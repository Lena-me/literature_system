from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import fitz

from app.core.config import get_settings
from app.utils.text_utils import normalize_text

settings = get_settings()


class MinerUParser:
    """MinerU CLI adapter that returns the existing parser result shape."""

    # ---------- 学位论文前置垃圾页关键词 ----------
    _THESIS_JUNK_PATTERNS = [
        r'答辩委员会',
        r'决议书',
        r'中图分类号',
        r'UDC',
        r'学校代码',
        r'学\s*号',
        r'密\s*级',
        r'授予学位单位',
        r'原创性声明',
        r'授权使用说明',
        r'学位论文版权使用授权书',
        r'学位论文原创性声明',
        r'关于学位论文使用授权的说明',
        r'保密\s*□?\s*年',
        r'指导教师',
        r'专业名称',
        r'学位类别',
        r'作者姓名',
        r'学院\s*[:：]',
        r'分类号',
    ]
    _THESIS_JUNK_RE = re.compile('|'.join(_THESIS_JUNK_PATTERNS))

    # ---------- 中文参考文献识别正则 ----------
    # 匹配: [1] 作者. 标题[J]. 期刊, 年份
    _CN_REF_PATTERN = re.compile(
        r'^\[\s*\d+(?:\s*[,，\-]\s*\d+)*\s*\].*?[JDCMPN]\s*[\.。]',
    )

    # ---------- 英文参考文献识别正则 ----------
    # 匹配: [1] J. Smith, et al., "Title," Journal, 2020.  / [1] J Smith et al. Title. Journal. 2020.
    _EN_REF_PATTERN = re.compile(
        r'^\[\s*\d+(?:\s*[,，\-]\s*\d+)*\s*\].*?(?:(?:\b(?:et\s+al|and)\b)|(?:[A-Z][a-z]+[,.]\s+[A-Z]\.)|(?:",?\s*".*?",))',
    )
    # 英文参考文献续行特征：DOI、页码范围、末尾年份、会议缩写
    _EN_REF_CONTINUATION_RE = re.compile(
        r'(doi:|DOI:|https?://doi\.org/|pp?\.\s*\d+[-–]\d+|'
        r'\b(?:Proc\.|Conf\.|Journal|Trans\.|ACM|IEEE|Springer|arXiv)\b|'
        r'[A-Z][a-z]+\s+et\s+al\.?|'
        r'\d{4}[.;,]?\s*$|'
        r'(?:vol\.?|pp\.?|no\.?)\s*\d+)',
        re.I,
    )

    # ---------- 公式检测正则 ----------
    # MinerU 经常把公式块误判为 paragraph，丢失了 $$ 包裹。
    # 此正则检测 LaTeX 公式特征命令，用于升维为 formula。
    _FORMULA_SIGNAL_RE = re.compile(
        r'\\(?:frac|sum|prod|int|lim|log|sqrt|mathrm|mathbb|mathcal|mathbf|'
        r'begin|end|tag|label|operatorname|DeclareMathOperator|'
        r'left|right|times|div|pm|nabla|partial|infty|approx|'
        r'alpha|beta|gamma|delta|epsilon|sigma|lambda|mu|pi|theta|omega|'
        r'overline|underline|hat|tilde|bar|dot|vec|'
        r'text|textbf|textit|'
        r'Delta|Sigma|Omega|Pi|Gamma|Lambda|Theta|Phi)'
    )
    # 匹配结尾有 $$ 但开头没有的孤立公式（MinerU 切割 bug）
    _ORPHAN_CLOSING_RE = re.compile(r'\$\$\s*$')

    def parse(self, pdf_bytes: bytes, filename: str) -> dict:
        job_id = uuid4().hex
        base_output_dir = Path(settings.mineru_output_dir)
        base_output_dir.mkdir(parents=True, exist_ok=True)

        job_output_dir = base_output_dir / job_id
        job_output_dir.mkdir(parents=True, exist_ok=True)

        safe_name = self._safe_filename(filename)
        input_pdf = job_output_dir / safe_name
        input_pdf.write_bytes(pdf_bytes)

        try:
            self._run_mineru(input_pdf, job_output_dir)

            content_json = self._load_content_json(job_output_dir)
            markdown_text = self._load_markdown(job_output_dir)
            parsed = self._convert_outputs(
                markdown_text=markdown_text,
                content_json=content_json,
                pdf_bytes=pdf_bytes,
                filename=filename,
            )
            parsed['parser'] = 'mineru'
            parsed['mineru_output_dir'] = str(job_output_dir)

            # 在 cleanup 前收集图片数据，供 pipeline_service 上传到 MinIO
            parsed['_image_data'] = self._collect_output_images(
                job_output_dir,
                parsed.get('figures_tables', []),
            )

            return parsed
        finally:
            if not settings.mineru_keep_output:
                shutil.rmtree(job_output_dir, ignore_errors=True)

    def _run_mineru(self, input_pdf: Path, output_dir: Path) -> None:
        cmd = [
            settings.mineru_command,
            '-p',
            str(input_pdf),
            '-o',
            str(output_dir),
        ]

        if settings.mineru_backend:
            cmd.extend(['-b', settings.mineru_backend])

        if settings.mineru_method:
            cmd.extend(['-m', settings.mineru_method])
        if settings.mineru_language:
            cmd.extend(['-l', settings.mineru_language])
        if settings.mineru_api_url:
            cmd.extend(['--api-url', settings.mineru_api_url])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                check=False,
                text=True,
                timeout=settings.mineru_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f'MinerU parse timed out after {settings.mineru_timeout_seconds}s'
            ) from exc

        if proc.returncode != 0:
            stdout = (proc.stdout or '')[-2000:]
            stderr = (proc.stderr or '')[-4000:]
            raise RuntimeError(
                f'MinerU parse failed: returncode={proc.returncode}\n'
                f'STDOUT:\n{stdout}\nSTDERR:\n{stderr}'
            )

    def _convert_outputs(
        self,
        markdown_text: str,
        content_json,
        pdf_bytes: bytes,
        filename: str,
    ) -> dict:
        pages = self._parse_pages_with_pymupdf(pdf_bytes)
        json_items, json_figures = self._items_from_content_json(content_json)

        if json_items:
            content_items = json_items
            figures_tables = json_figures
        else:
            content_items, figures_tables = self._items_from_markdown(markdown_text)

        if not content_items:
            content_items = [
                {
                    'item_type': 'paragraph',
                    'level': None,
                    'content': page['text'],
                    'page_number': page['page_number'],
                    'order_index': idx,
                }
                for idx, page in enumerate(pages)
                if page.get('text')
            ]
        content_items = self._post_process_items(content_items)

        metadata = self._extract_metadata(markdown_text, content_items, filename)
        return {
            'metadata': metadata,
            'content_items': content_items,
            'figures_tables': figures_tables,
            'references': [],
            'pages': pages,
            'markdown': markdown_text,
        }

    def _load_markdown(self, output_dir: Path) -> str:
        md_files = list(output_dir.rglob('*.md'))
        if not md_files:
            return ''

        md_files.sort(key=lambda p: p.stat().st_size, reverse=True)
        for path in md_files:
            try:
                text = path.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            if text.strip():
                return text
        return ''

    def _load_content_json(self, output_dir: Path):

        """
        MinerU emits content_list/content_list_v2 plus intermediate files such
        as middle/model. Prefer content_list outputs for stable reading order.
        """
        json_files = list(output_dir.rglob('*.json'))
        if not json_files:
            return None

        def score(path: Path) -> tuple[int, int]:
            name = path.name.lower()
            if 'content_list_v2' in name:
                rank = 0
            elif 'content_list' in name:
                rank = 1
            elif 'middle' in name:
                rank = 2
            elif 'model' in name:
                rank = 3
            else:
                rank = 9
            return rank, -path.stat().st_size

        for path in sorted(json_files, key=score):
            try:
                data = json.loads(path.read_text(encoding='utf-8', errors='ignore'))
            except Exception:
                continue
            if data:
                return data
        return None

    def _items_from_content_json(self, data) -> tuple[list[dict], list[dict]]:
        if not data:
            return [], []

        if isinstance(data, dict):
            if isinstance(data.get('content_list'), list):
                blocks = data.get('content_list') or []
            elif isinstance(data.get('pages'), list):
                blocks = []
                for page in data.get('pages') or []:
                    if isinstance(page, dict):
                        blocks.extend(page.get('blocks') or page.get('content') or [])
            elif isinstance(data.get('blocks'), list):
                blocks = data.get('blocks') or []
            else:
                blocks = []
        elif isinstance(data, list):
            blocks = data
        else:
            blocks = []

        content_items: list[dict] = []
        figures_tables: list[dict] = []
        order = 0

        for block in blocks:
            if not isinstance(block, dict):
                continue

            block_type = str(
                block.get('type')
                or block.get('block_type')
                or block.get('category')
                or block.get('category_type')
                or ''
            ).lower()

            page_number = block.get('page_number') or block.get('page_no') or block.get('page')
            page_idx = block.get('page_idx')
            if page_number is None and isinstance(page_idx, int):
                page_number = page_idx + 1

            text_level = block.get('text_level') or block.get('level')
            level = self._to_int(text_level, default=1) if text_level not in (None, '') else None

            if 'table' in block_type:
                caption = self._stringify_mineru_value(
                    block.get('table_caption') or block.get('caption') or block.get('text') or ''
                )
                raw_body = block.get('table_body') or block.get('html') or block.get('content') or block.get('text') or ''
                body = self._format_table_body(raw_body)

                footnote = self._stringify_mineru_value(block.get('table_footnote') or '')
                table_text = normalize_text('\n'.join(x for x in [caption, body, footnote] if x))
                if not table_text:
                    continue

                figures_tables.append(
                    {
                        'type': 'table',
                        'caption': caption or 'Table extracted by MinerU',
                        'page_number': page_number,
                        'extracted_text': table_text,
                        'order_index': len(figures_tables),
                    }
                )
                content_items.append(
                    {
                        'item_type': 'table',
                        'level': None,
                        'content': table_text,
                        'page_number': page_number,
                        'order_index': order,
                    }
                )
                order += 1
                continue

            if 'image' in block_type or 'figure' in block_type:
                caption = self._stringify_mineru_value(
                    block.get('img_caption') or block.get('caption') or block.get('text') or ''
                )
                footnote = self._stringify_mineru_value(block.get('img_footnote') or '')
                extracted_text = normalize_text('\n'.join(x for x in [caption, footnote] if x))
                image_path = block.get('img_path') or block.get('image_path') or block.get('path')

                figures_tables.append(
                    {
                        'type': 'figure',
                        'caption': caption or 'Figure extracted by MinerU',
                        'page_number': page_number,
                        'image_path': str(image_path) if image_path else None,
                        'extracted_text': extracted_text,
                        'order_index': len(figures_tables),
                    }
                )
                md_image = self._build_image_markdown(caption, image_path)
                content_items.append(
                    {
                        'item_type': 'figure',
                        'level': None,
                        'content': md_image,
                        'page_number': page_number,
                        'order_index': order,
                    }
                )
                order += 1

                continue

            text = self._stringify_mineru_value(
                block.get('text')
                or block.get('content')
                or block.get('html')
                or block.get('caption')
                or ''
            )
            text = normalize_text(text)
            if not text:
                continue

            if 'title' in block_type or 'heading' in block_type or level is not None:
                item_type = 'heading'
                item_level = level or 1
            elif 'equation' in block_type or 'formula' in block_type:
                item_type = 'formula'
                item_level = None
            else:
                item_type = 'paragraph'
                item_level = None

            content_items.append(
                {
                    'item_type': item_type,
                    'level': item_level,
                    'content': text,
                    'page_number': page_number,
                    'order_index': order,
                }
            )
            order += 1

        return content_items, figures_tables

    def _items_from_markdown(self, markdown_text: str) -> tuple[list[dict], list[dict]]:
        content_items: list[dict] = []
        figures_tables: list[dict] = []
        if not markdown_text.strip():
            return content_items, figures_tables

        lines = markdown_text.splitlines()
        order = 0
        paragraph_buffer: list[str] = []

        def flush_paragraph() -> None:
            nonlocal order
            text = normalize_text('\n'.join(paragraph_buffer).strip())
            paragraph_buffer.clear()
            if not text:
                return
            content_items.append(
                {
                    'item_type': 'paragraph',
                    'level': None,
                    'content': text,
                    'page_number': None,
                    'order_index': order,
                }
            )
            order += 1

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                flush_paragraph()
                i += 1
                continue

            heading = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading:
                flush_paragraph()
                content_items.append(
                    {
                        'item_type': 'heading',
                        'level': len(heading.group(1)),
                        'content': normalize_text(heading.group(2)),
                        'page_number': None,
                        'order_index': order,
                    }
                )
                order += 1
                i += 1
                continue

            image = re.match(r'^!\[(.*?)\]\((.*?)\)', line)
            if image:
                flush_paragraph()
                figures_tables.append(
                    {
                        'type': 'figure',
                        'caption': normalize_text(image.group(1) or 'Figure extracted by MinerU'),
                        'page_number': None,
                        'image_path': image.group(2) or None,
                        'extracted_text': line,
                        'order_index': len(figures_tables),
                    }
                )
                content_items.append(
                    {
                        'item_type': 'figure',
                        'level': None,
                        'content': line,
                        'page_number': None,
                        'order_index': order,
                    }
                )
                order += 1

                i += 1
                continue

            if self._looks_like_table_line(line):
                flush_paragraph()
                table_lines = []
                while i < len(lines) and self._looks_like_table_line(lines[i].strip()):
                    table_lines.append(lines[i].strip())
                    i += 1
                table_text = '\n'.join(table_lines)
                figures_tables.append(
                    {
                        'type': 'table',
                        'caption': 'Table extracted by MinerU',
                        'page_number': None,
                        'extracted_text': table_text,
                        'order_index': len(figures_tables),
                    }
                )
                content_items.append(
                    {
                        'item_type': 'table',

                        'level': None,
                        'content': table_text,
                        'page_number': None,
                        'order_index': order,
                    }
                )
                order += 1
                continue

            paragraph_buffer.append(line)
            i += 1

        flush_paragraph()
        return content_items, figures_tables

    def _looks_like_table_line(self, line: str) -> bool:
        return line.count('|') >= 2

    # ======================== 辅助方法 ========================

    @staticmethod
    def _build_image_markdown(caption: str, image_path) -> str:
        """将图片组装为标准 Markdown 图片语法 ![caption](image_path)。
        自动将 Windows 反斜杠转为正斜杠，确保 URL 有效。"""
        cap = (caption or '').strip()
        path = str(image_path or '').strip()
        if path:
            path = path.replace('\\', '/')
            return f'![{cap}]({path})'
        return cap

    @staticmethod
    def _format_table_body(raw_body) -> str:
        """将表格 body 格式化为可渲染文本：2D数组→Markdown表格，HTML→转Markdown，纯文本→原样返回。"""
        # 严格二维数组 (list[list]) → 转 Markdown 表格
        if isinstance(raw_body, list) and len(raw_body) > 0 and isinstance(raw_body[0], list):
            lines = []
            for i, row in enumerate(raw_body):
                if isinstance(row, list):
                    cells = [str(cell) for cell in row]
                    lines.append('| ' + ' | '.join(cells) + ' |')
                    if i == 0:
                        lines.append('| ' + ' | '.join('---' for _ in cells) + ' |')
                else:
                    lines.append(str(row))
            return '\n'.join(lines)

        text = raw_body if isinstance(raw_body, str) else json.dumps(raw_body, ensure_ascii=False)
        # HTML 表格 → 尝试转为 Markdown 表格
        if '<table' in text.lower():
            md = MinerUParser._convert_html_table_to_markdown(text)
            return md
        return text

    @staticmethod
    def _convert_html_table_to_markdown(html_text: str) -> str:
        """解析 HTML <table> 并转为 Markdown 表格，解析失败则原样返回。"""
        # 提取所有 <tr>...</tr>
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.I | re.S)
        if not rows:
            return html_text

        lines = []
        for i, row in enumerate(rows):
            # 提取 <td> 或 <th> 内容
            cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.I | re.S)
            if not cells:
                continue
            clean_cells = [re.sub(r'<[^>]+>', '', c).replace('\n', ' ').strip() for c in cells]
            lines.append('| ' + ' | '.join(clean_cells) + ' |')
            if i == 0:
                lines.append('| ' + ' | '.join('---' for _ in clean_cells) + ' |')

        return '\n'.join(lines) if lines else html_text

    @staticmethod
    def _is_html_garbage(text: str) -> bool:
        """检测文本是否为纯 HTML 碎片（标签占比过高）。"""
        text = text.strip()
        if not text:
            return False
        if not re.search(r'<\s*(table|tr|td|th|thead|tbody|colgroup|col|img|br|hr|div|span|p)\b', text, re.I):
            return False
        clean = re.sub(r'<[^>]+>', '', text).strip()
        ratio = len(clean) / max(len(text), 1)
        return ratio < 0.2

    @staticmethod
    def _collect_output_images(output_dir: Path, figures_tables: list[dict]) -> dict[str, bytes]:
        """在目录被清理前，收集所有被引用的图片文件内容。"""
        import logging
        logger = logging.getLogger(__name__)

        image_data: dict[str, bytes] = {}
        output_dir = Path(output_dir)
        found = 0
        missed = 0

        for ft in figures_tables:
            if ft.get('type') != 'figure':
                continue
            img_path = ft.get('image_path')
            if not img_path:
                continue

            img_file = Path(img_path)
            if not img_file.is_absolute():
                img_file = output_dir / img_file
            if not img_file.is_file():
                candidates = list(output_dir.rglob(img_file.name))
                if candidates:
                    img_file = candidates[0]
                else:
                    missed += 1
                    logger.warning('Image file not found: %s (searched in %s)', img_path, output_dir)
                    continue

            try:
                # 使用正斜杠作为 key，与 _build_image_markdown 保持一致
                normalized_key = img_path.replace('\\', '/')
                image_data[normalized_key] = img_file.read_bytes()
                found += 1
            except Exception as e:
                missed += 1
                logger.warning('Failed to read image %s: %s', img_file, e)
                continue

        logger.info('Collected %d figure images (%d missed) from %s', found, missed, output_dir)
        return image_data

    # ============================================================
    def _extract_metadata(self, markdown_text: str, content_items: list[dict], filename: str) -> dict:
        title = ''

        for item in content_items[:20]:
            text = normalize_text(str(item.get('content') or ''))
            if item.get('item_type') == 'heading' and len(text) >= 8:
                if not re.search(r'^(abstract|摘要|keywords?|关键词|关键字|index terms)\b', text, flags=re.I):
                    title = text.strip('# ').strip()
                    break

        if not title:
            for line in markdown_text.splitlines()[:80]:
                line = normalize_text(line.strip('#').strip())
                if not line or line.startswith('!['):
                    continue
                if re.search(r'^(abstract|摘要|keywords?|关键词|关键字|index terms)\b', line, flags=re.I):
                    continue
                if len(line) >= 8:
                    title = line
                    break

        return {
            'title': title or filename,
            'authors': [],
            'keywords': self._extract_keywords(markdown_text, content_items),
            'abstract': self._extract_abstract(content_items),
        }

    def _extract_abstract(self, content_items: list[dict]) -> str:
        for idx, item in enumerate(content_items):
            text = item.get('content') or ''
            if item.get('item_type') == 'heading' and re.search(r'摘要|abstract', text, flags=re.I):
                parts = []
                for nxt in content_items[idx + 1:]:
                    if nxt.get('item_type') == 'heading':
                        break
                    if nxt.get('content'):
                        parts.append(nxt['content'])
                return normalize_text('\n'.join(parts))

        for item in content_items[:40]:
            text = item.get('content') or ''
            if re.match(r'^(摘要|Abstract)\s*[:：]', text, flags=re.I):
                return normalize_text(re.sub(r'^(摘要|Abstract)\s*[:：]\s*', '', text, flags=re.I))
        return ''

    def _extract_keywords(self, markdown_text: str, content_items: list[dict]) -> list[str]:
        candidates: list[str] = []
        patterns = [
            r'(?:keywords?|index\s+terms)\s*[:：]\s*(.+?)(?=\n\n|\n[A-Z]|\Z)',
            r'(?:关键词|关键字)\s*[:：]\s*(.+?)(?=\n\n|\Z)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, markdown_text, flags=re.I | re.S):
                candidates.append(match.group(1))

        for idx, item in enumerate(content_items):
            text = normalize_text(str(item.get('content') or ''))
            if item.get('item_type') == 'heading' and re.search(
                r'keywords?|index\s+terms|关键词|关键字',
                text,
                flags=re.I,
            ):
                keyword_lines = []
                for nxt in content_items[idx + 1: idx + 6]:
                    if nxt.get('item_type') == 'heading':
                        break
                    if nxt.get('content'):
                        keyword_lines.append(str(nxt.get('content')))
                if keyword_lines:
                    candidates.append(' '.join(keyword_lines))

        for idx, item in enumerate(content_items):
            text = normalize_text(str(item.get('content') or ''))
            if re.match(r'^(keywords?|关键词|关键字)\s*[:：]', text, flags=re.I):
                candidates.append(text)
                for nxt in content_items[idx + 1: idx + 4]:
                    if nxt.get('item_type') == 'heading':
                        break
                    if nxt.get('content'):
                        candidates.append(str(nxt.get('content')))

        joined = '；'.join(candidates)

        if not joined:
            joined = self._extract_keywords_from_content(content_items)

        if not joined:
            return []

        joined = re.sub(
            r'\b(CCS Concepts|ACM Reference Format|Additional Key Words).*',
            '',
            joined,
            flags=re.I | re.S,
        )

        raw_terms = re.split(r'[;；,，、\n]+', joined)
        result: list[str] = []
        seen: set[str] = set()

        for term in raw_terms:
            term = normalize_text(term.strip(' .;；,，:：'))
            if not term or len(term) > 80:
                continue

            key = term.lower()
            if key not in seen:
                result.append(term)
                seen.add(key)

            if len(result) >= 12:
                break

        return result

    def _extract_keywords_from_content(self, content_items: list[dict]) -> str:
        title_text = ''
        abstract_text = ''
        heading_text = ''
        paragraph_text = ''

        for item in content_items[:150]:
            text = normalize_text(str(item.get('content') or ''))
            if not text:
                continue

            if item.get('item_type') == 'heading':
                if item.get('level') == 1 and not title_text:
                    title_text = text
                elif re.search(r'摘要|abstract', text, flags=re.I):
                    continue
                else:
                    heading_text += text + ' '
            elif re.match(r'^(摘要|Abstract)\s*[:：]', text, flags=re.I):
                abstract_text = text + ' '
            elif item.get('item_type') == 'paragraph' and len(paragraph_text) < 3000:
                paragraph_text += text[:800] + ' '

        all_text = title_text + ' ' + abstract_text + ' ' + heading_text + ' ' + paragraph_text
        return self._extract_keywords_from_text(all_text)

    def _extract_keywords_from_text(self, text: str) -> str:
        text = normalize_text(text)
        if not text:
            return ''

        cn_pattern = r'[\u4e00-\u9fa5]{2,8}'
        en_pattern = r'[A-Z][a-zA-Z0-9_-]{2,18}'

        cn_matches = re.findall(cn_pattern, text)
        en_matches = re.findall(en_pattern, text)

        stop_words = {
            '摘要', 'abstract', '引言', 'introduction', '结论', 'conclusion',
            '参考文献', 'references', '致谢', 'acknowledgments', '附录', 'appendix',
            '研究', '方法', '结果', '分析', '讨论', '提出', '基于', '使用',
            '通过', '实现', '表明', '显示', '发现', '认为', '可能', '可以', '已经',
            '本文', '本研究', '近年来', '目前', '随着', '由于', '因此', '然而',
            '但是', '同时', '并且', '以及', '包括', '例如', '比如', '等等',
            '一些', '许多', '大量', '部分', '全部', '主要', '重要', '关键',
            'first', 'second', 'third', 'last', 'finally', 'also', 'and', 'or',
            'but', 'not', 'this', 'that', 'these', 'those', 'with', 'for', 'of',
            'in', 'on', 'at', 'to', 'from', 'by', 'as', 'is', 'are', 'was', 'were',
            'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall',
            'can', 'cannot', 'need', 'want', 'like', 'get', 'make', 'take', 'give',
            'go', 'come', 'know', 'think', 'see', 'look', 'feel', 'say', 'tell',
            'ask', 'answer', 'find', 'show', 'use', 'work', 'study', 'research',
            'paper', 'article', 'document', 'system', 'method', 'approach', 'technique',
            'algorithm', 'model', 'framework', 'tool', 'software', 'hardware',
            'data', 'information', 'knowledge', 'result', 'analysis', 'evaluation',
            'performance', 'experiment', 'test', 'case', 'example', 'application',
            'implementation', 'development', 'design', 'structure', 'architecture',
        }

        cn_counter: dict[str, int] = {}
        for word in cn_matches:
            if word.lower() not in stop_words and len(word) >= 2:
                cn_counter[word] = cn_counter.get(word, 0) + 1

        en_counter: dict[str, int] = {}
        for word in en_matches:
            if word.lower() not in stop_words and len(word) >= 3:
                en_counter[word] = en_counter.get(word, 0) + 1

        cn_sorted = sorted(cn_counter.items(), key=lambda x: x[1], reverse=True)[:10]
        en_sorted = sorted(en_counter.items(), key=lambda x: x[1], reverse=True)[:10]

        all_keywords = [k for k, v in cn_sorted] + [k for k, v in en_sorted]
        return '，'.join(all_keywords[:12])

    def _extract_authors(self, markdown_text: str, title: str) -> list[str]:
        lines = [
            normalize_text(x.strip())
            for x in markdown_text.splitlines()[:80]
            if normalize_text(x.strip())
        ]
        if not lines:
            return []

        start = 0
        if title:
            for i, line in enumerate(lines[:30]):
                if title.lower() in line.lower() or line.lower() in title.lower():
                    start = i + 1
                    break

        author_lines = []
        for line in lines[start:start + 12]:
            if re.search(r'^(abstract|摘要|keywords?|关键词|关键字|index terms|introduction)\b', line, flags=re.I):
                break
            if '@' in line or re.search(
                r'\b(university|institute|school|department|laboratory|college)\b',
                line,
                flags=re.I,
            ):
                continue
            if 2 <= len(line) <= 250:
                author_lines.append(line)

        if not author_lines:
            return []

        text = ' '.join(author_lines[:3])
        text = re.sub(r'\d+|[*\u2020\u2021\u00a7]|\([^)]*\)', ' ', text)

        parts = re.split(r'\s*,\s*|\s+and\s+|；|;|、', text)
        authors = []
        seen = set()

        for part in parts:
            part = normalize_text(part.strip())
            if not part or len(part) > 60:
                continue
            if re.search(
                r'\b(abstract|keywords|university|institute|department|school)\b',
                part,
                flags=re.I,
            ):
                continue
            key = part.lower()
            if key not in seen:
                authors.append(part)
                seen.add(key)

            if len(authors) >= 20:
                break

        return authors

    def _post_process_items(self, items: list[dict]) -> list[dict]:
        """后置清洗：剔除目录/封面垃圾、修复标题降维、合并断行与引用（中英文）"""

        cleaned_items = []

        for item in items:
            if item.get('item_type') not in ('paragraph', 'heading', 'list', 'abstract'):
                cleaned_items.append(item)
                continue

            text = str(item.get('content', '')).strip()
            if not text:
                continue

            # ---------- 0a. 纯 HTML 块清洗 ----------
            if self._is_html_garbage(text):
                order_idx = item.get('order_index', 999)
                if isinstance(order_idx, (int, float)) and order_idx < 15:
                    continue

            # ---------- 0b. 学位论文封面/声明页特征词 ----------
            text_no_space = text.replace(' ', '').replace('\n', '').replace('\r', '')
            if len(text_no_space) < 200:
                if self._THESIS_JUNK_RE.search(text_no_space):
                    continue
                if len(text_no_space) < 30 and re.match(
                    r'^(分类号|UDC|密级|学校代码|学号|指导教师|专业名称|学位类别|作者姓名|学院|答辩委员会|答辩日期|原创性声明|授权使用说明)',
                    text_no_space,
                ):
                    continue
                if len(text) < 15 and not re.search(r'[。！？：:;.!?]$', text) and (
                    '学位' in text or text in ['公开', '保密', '内部']
                ):
                    continue

            # ---------- 1. 剔除目录 (TOC 污染清洗) ----------
            if re.search(r'(?:\.{3,}|\u2026{2,})\s*\d+$', text):
                continue
            if re.match(r'^(目录|Contents?|图目录|表目录)$', text, re.I):
                continue

            # ---------- 2. 标题强升维 ----------
            if item.get('item_type') in ('paragraph', 'list') and len(text) < 100 and not re.search(r'[。！？;.!?]$', text):
                if re.match(r'^第[一二三四五六七八九十\d]+章\s*[\u4e00-\u9fa5a-zA-Z]', text):
                    item['item_type'] = 'heading'
                    item['level'] = 1
                elif re.match(r'^\d+\.\d+\.\d+\s*[\u4e00-\u9fa5a-zA-Z]', text):
                    item['item_type'] = 'heading'
                    item['level'] = 3
                elif re.match(r'^\d+\.\d+\s*[\u4e00-\u9fa5a-zA-Z]', text):
                    item['item_type'] = 'heading'
                    item['level'] = 2
                elif re.match(r'^\d+\.\s+[\u4e00-\u9fa5a-zA-Z]', text):
                    item['item_type'] = 'heading'
                    item['level'] = 1
                elif re.match(r'^[IVX]+\.\s+[A-Z\s]+$', text):
                    item['item_type'] = 'heading'
                    item['level'] = 1

            item['content'] = text
            cleaned_items.append(item)

        # ---------- 2.5 公式升维：检测被 MinerU 误判为 paragraph 的 LaTeX 公式 ----------
        for item in cleaned_items:
            if item.get('item_type') not in ('paragraph', 'list'):
                continue

            content = item.get('content', '').strip()
            if not content:
                continue

            # MinerU 已输出完整 $$...$$ 包裹，只需升维
            if content.startswith('$$') and content.endswith('$$'):
                item['item_type'] = 'formula'
                continue

            # 无 $$ 包裹但有 LaTeX 命令 → 补包裹后升维
            if self._FORMULA_SIGNAL_RE.search(content):
                # 去掉尾部可能附着的孤立 $$
                content = self._ORPHAN_CLOSING_RE.sub('', content).strip()
                item['content'] = '$$\n' + content + '\n$$'
                item['item_type'] = 'formula'

        # ---------- 3. 硬回车断行与引用割裂合并（中英文） ----------
        final_items = []
        for item in cleaned_items:
            curr_type = item.get('item_type')
            if final_items and curr_type in ('paragraph', 'list') and final_items[-1].get('item_type') in (
            'paragraph', 'list'):
                prev_text = final_items[-1]['content'].strip()
                curr_text = item['content'].strip()
                ends_without_period = not re.search(r'[。！？：:;.!?]["\u201c\u201d\'\u2019\)\]）】]?$', prev_text)
                starts_with_citation = bool(re.match(r'^\[\s*\d+(?:\s*[,，\-]\s*\d+)*\]', curr_text))
                is_standalone_citation = bool(re.match(r'^\[\s*\d+(?:\s*[,，\-]\s*\d+)*\][。！？.!?]?$', curr_text))
                starts_with_lowercase = bool(re.match(r'^[a-z]', curr_text))

                # 中文参考文献
                prev_is_cn_ref = bool(self._CN_REF_PATTERN.search(prev_text))
                # 中文参考文献续行
                curr_is_cn_ref_continuation = bool(
                    not re.match(r'^\[\s*\d+', curr_text)
                    and (
                        re.search(r'[JDCMPN]\s*[\.。]', curr_text)
                        or re.search(r'\d{4}[,，]\s*\d+', curr_text)
                        or re.search(r'(in Chinese|\(in Chinese\)|doi:|DOI:)', curr_text, re.I)
                    )
                )

                # 英文参考文献
                prev_is_en_ref = bool(
                    self._EN_REF_PATTERN.search(prev_text)
                    and not prev_is_cn_ref
                )
                # 英文参考文献续行
                curr_is_en_ref_continuation = bool(
                    not re.match(r'^\[\s*\d+', curr_text)
                    and self._EN_REF_CONTINUATION_RE.search(curr_text)
                )
                should_merge = False

                if ends_without_period:
                    should_merge = True
                elif starts_with_citation or is_standalone_citation:
                    should_merge = True
                elif starts_with_lowercase:
                    should_merge = True
                # 中文参考文献续行
                elif prev_is_cn_ref and ends_without_period:
                    should_merge = True
                elif prev_is_cn_ref and curr_is_cn_ref_continuation:
                    should_merge = True
                # 英文参考文献续行
                elif prev_is_en_ref and ends_without_period:
                    should_merge = True
                elif prev_is_en_ref and curr_is_en_ref_continuation:
                    should_merge = True

                if should_merge:
                    final_items[-1]['item_type'] = 'paragraph'
                    if re.search(r'[a-zA-Z0-9]$', prev_text) and re.match(r'^[a-zA-Z0-9\[\(]', curr_text):
                        final_items[-1]['content'] = f"{prev_text} {curr_text}"
                    else:
                        final_items[-1]['content'] = f"{prev_text}{curr_text}"
                    continue

            final_items.append(item)

        return final_items

    def _stringify_mineru_value(self, value) -> str:
        if value is None:
            return ''
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return '\n'.join(self._stringify_mineru_value(x) for x in value if x is not None)
        if isinstance(value, dict):
            for key in ('text', 'content', 'html', 'caption'):
                if key in value:
                    return self._stringify_mineru_value(value.get(key))
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _parse_pages_with_pymupdf(self, pdf_bytes: bytes) -> list[dict]:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype='pdf')
            pages = [
                {'page_number': i, 'text': normalize_text(page.get_text('text'))}
                for i, page in enumerate(doc, start=1)
            ]
            doc.close()
            return pages
        except Exception:
            return []

    def _safe_filename(self, filename: str) -> str:
        name = Path(filename or 'input.pdf').name
        name = re.sub(r'[^\w.\-()\u4e00-\u9fa5]+', '_', name)
        if not name.lower().endswith('.pdf'):
            name = f'{name}.pdf'
        return name

    def _to_int(self, value, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default
