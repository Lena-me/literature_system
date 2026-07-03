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
        r'\\(?:frac|sum|prod|int|lim|log|sqrt|mathrm|mathbb|mathcal|mathbf|mathit|'
        r'begin|end|tag|label|operatorname|DeclareMathOperator|'
        r'left|right|times|div|pm|nabla|partial|infty|approx|'
        r'alpha|beta|gamma|delta|epsilon|varepsilon|sigma|lambda|mu|pi|theta|omega|'
        r'cdot|qquad|quad|in|vert|'
        r'overline|underline|hat|tilde|bar|dot|vec|'
        r'text|textbf|textit|'
        r'Delta|Sigma|Omega|Pi|Gamma|Lambda|Theta|Phi)'
    )
    _TAG_RE = re.compile(r'\\tag\s*\{([^}]*)\}')
    _CJK_RE = re.compile(r'[\u4e00-\u9fff]')
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
                    'bbox': None,
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

    def _flatten_content_json_blocks(self, data) -> list[dict]:
        """展开 MinerU content_list_v2 的「页 → 块」嵌套结构。"""
        if isinstance(data, dict):
            if isinstance(data.get('content_list'), list):
                raw = data.get('content_list') or []
            elif isinstance(data.get('pages'), list):
                blocks: list[dict] = []
                for page_idx, page in enumerate(data.get('pages') or []):
                    if isinstance(page, dict):
                        page_blocks = page.get('blocks') or page.get('content') or []
                    elif isinstance(page, list):
                        page_blocks = page
                    else:
                        continue
                    for block in page_blocks:
                        if isinstance(block, dict):
                            enriched = dict(block)
                            enriched.setdefault('page_idx', page_idx)
                            blocks.append(enriched)
                return blocks
            elif isinstance(data.get('blocks'), list):
                raw = data.get('blocks') or []
            else:
                return []
        elif isinstance(data, list):
            raw = data
        else:
            return []

        if not raw:
            return []

        if all(isinstance(page, list) for page in raw):
            blocks = []
            for page_idx, page in enumerate(raw):
                for block in page:
                    if isinstance(block, dict):
                        enriched = dict(block)
                        enriched.setdefault('page_idx', page_idx)
                        blocks.append(enriched)
            return blocks

        return [block for block in raw if isinstance(block, dict)]

    @staticmethod
    def _normalize_bbox(bbox) -> list[float] | None:
        """MinerU bbox 为 0~1000 比例坐标（左上原点），统一存为 [x0,y0,x1,y1]（0~1）。"""
        if not bbox:
            return None
        if isinstance(bbox, dict):
            if all(k in bbox for k in ('left', 'top', 'width', 'height')):
                left = float(bbox['left'])
                top = float(bbox['top'])
                width = float(bbox['width'])
                height = float(bbox['height'])
                return [left, top, left + width, top + height]
            return None
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return None
        try:
            x0, y0, x1, y1 = (float(v) for v in bbox)
        except (TypeError, ValueError):
            return None
        if max(x0, y0, x1, y1) <= 1.0:
            return [x0, y0, x1, y1]
        scale = 1000.0 if max(x0, y0, x1, y1) <= 1000.0 else max(x1, y1)
        return [x0 / scale, y0 / scale, x1 / scale, y1 / scale]

    def _block_bbox(self, block: dict) -> list[float] | None:
        return self._normalize_bbox(block.get('bbox'))

    @staticmethod
    def _normalize_latex_for_katex(latex: str) -> str:
        """收紧 MinerU 松散 LaTeX，并替换 KaTeX 不支持的 \\tag。"""
        text = latex.strip()
        if not text:
            return text

        text = MinerUParser._TAG_RE.sub(r'\\quad\\text{(\1)}', text)
        text = re.sub(
            r'\\(mathit|mathrm|mathbf|mathcal|mathbb|mathfrak|mathsf|mathtt)\s*\{\s*([^}]+?)\s*\}',
            lambda m: f'\\{m.group(1)}{{{"".join(m.group(2).split())}}}',
            text,
        )
        text = re.sub(
            r'\\operatorname\s*\*\s*\{\s*([^}]+?)\s*\}',
            lambda m: f'\\operatorname*{{{"".join(m.group(1).split())}}}',
            text,
        )
        text = re.sub(
            r'\\operatorname\s*\{\s*([^}]+?)\s*\}',
            lambda m: f'\\operatorname{{{"".join(m.group(1).split())}}}',
            text,
        )
        text = re.sub(
            r'_\s*\{\s*([^}]+?)\s*\}',
            lambda m: f'_{{{"".join(m.group(1).split())}}}',
            text,
        )
        text = re.sub(
            r'\^\s*\{\s*([^}]+?)\s*\}',
            lambda m: '^{' + ''.join(m.group(1).split()) + '}',
            text,
        )
        text = re.sub(r'\{\s+', '{', text)
        text = re.sub(r'\s+\}', '}', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _render_rich_content(self, spans) -> str:
        """将 v2 JSON 的 paragraph_content / title_content 转为 Markdown 文本。"""
        if not isinstance(spans, list):
            return self._stringify_mineru_value(spans)

        parts: list[str] = []
        for span in spans:
            if not isinstance(span, dict):
                continue
            span_type = str(span.get('type') or '').lower()
            raw = span.get('content') or span.get('text') or ''
            if isinstance(raw, dict):
                raw = self._stringify_mineru_value(raw)
            text = str(raw)
            if not text:
                continue
            if 'equation_inline' in span_type or span_type in ('inline', 'inline_formula'):
                latex = self._normalize_latex_for_katex(text)
                parts.append(f'${latex}$')
            else:
                parts.append(text)
        return normalize_text(''.join(parts))

    def _render_list_content(self, content: dict) -> str:
        """将 v2 JSON 的 list/index 块转为可读文本列表。"""
        if not isinstance(content, dict):
            return ''
        list_items = content.get('list_items') or []
        lines: list[str] = []
        for item in list_items:
            if not isinstance(item, dict):
                continue
            spans = item.get('item_content') or item.get('content') or []
            if isinstance(spans, dict):
                if spans.get('item_content') is not None:
                    spans = spans.get('item_content')
                elif spans.get('content') is not None:
                    spans = [spans]
                else:
                    spans = []
            line = self._render_rich_content(spans)
            if line:
                lines.append(line)
        return normalize_text('\n'.join(lines))

    @staticmethod
    def _extract_image_path(block: dict) -> str | None:
        """从 MinerU v1/v2 图片块提取相对路径。"""
        for key in ('img_path', 'image_path', 'path'):
            val = block.get(key)
            if val:
                return str(val).strip()
        content = block.get('content')
        if isinstance(content, dict):
            source = content.get('image_source') or {}
            if isinstance(source, dict):
                path = source.get('path')
                if path:
                    return str(path).strip()
        return None

    def _extract_image_caption(self, block: dict, block_content: dict | None = None) -> str:
        block_content = block_content if isinstance(block_content, dict) else block.get('content')
        for src in (block.get('img_caption'), block.get('caption'), block.get('text')):
            cap = self._stringify_mineru_value(src)
            if cap:
                return cap
        if isinstance(block_content, dict):
            cap_spans = block_content.get('image_caption') or block_content.get('caption')
            if isinstance(cap_spans, list):
                return self._render_rich_content(cap_spans)
            cap = self._stringify_mineru_value(cap_spans)
            if cap:
                return cap
        return ''

    def _extract_image_footnote(self, block: dict, block_content: dict | None = None) -> str:
        block_content = block_content if isinstance(block_content, dict) else block.get('content')
        footnote = self._stringify_mineru_value(block.get('img_footnote') or block.get('footnote') or '')
        if footnote:
            return footnote
        if isinstance(block_content, dict):
            spans = block_content.get('image_footnote') or block_content.get('footnote')
            if isinstance(spans, list):
                return self._render_rich_content(spans)
            return self._stringify_mineru_value(spans)
        return ''

    @staticmethod
    def _is_page_metadata_block(block_type: str) -> bool:
        return any(
            token in block_type
            for token in ('page_header', 'page_footer', 'page_number')
        )

    def _wrap_latex_content(self, latex: str, math_type: str = '') -> str:
        latex = self._normalize_latex_for_katex(latex)
        if not latex:
            return ''
        if math_type in ('equation_inline', 'inline', 'inline_formula'):
            return f'${latex}$'
        return f'$$\n{latex}\n$$'

    @staticmethod
    def _should_upgrade_paragraph_to_formula(content: str) -> bool:
        """仅将纯 LaTeX 段落升维为 formula，跳过中英文混排 + 行内公式。"""
        text = content.strip()
        if not text or (text.startswith('$$') and text.endswith('$$')):
            return False
        if '$' in text:
            return False
        if MinerUParser._CJK_RE.search(text):
            return False
        return bool(MinerUParser._FORMULA_SIGNAL_RE.search(text))

    def _items_from_content_json(self, data) -> tuple[list[dict], list[dict]]:
        if not data:
            return [], []

        blocks = self._flatten_content_json_blocks(data)

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

            if self._is_page_metadata_block(block_type):
                continue

            nested_content = block.get('content') if isinstance(block.get('content'), dict) else {}

            if 'table' in block_type:
                caption_spans = (
                    block.get('table_caption')
                    or block.get('caption')
                    or nested_content.get('table_caption')
                    or block.get('text')
                    or ''
                )
                if isinstance(caption_spans, list):
                    caption = self._render_rich_content(caption_spans)
                else:
                    caption = self._stringify_mineru_value(caption_spans)
                raw_body = (
                    block.get('table_body')
                    or block.get('html')
                    or nested_content.get('html')
                    or nested_content.get('table_body')
                    or (nested_content if nested_content else None)
                    or block.get('text')
                    or ''
                )
                body = self._format_table_body(raw_body)
                footnote_spans = block.get('table_footnote') or nested_content.get('table_footnote') or ''
                if isinstance(footnote_spans, list):
                    footnote = self._render_rich_content(footnote_spans)
                else:
                    footnote = self._stringify_mineru_value(footnote_spans)
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
                        'bbox': self._block_bbox(block),
                        'page_number': page_number,
                        'order_index': order,
                    }
                )
                order += 1
                continue

            if 'image' in block_type or 'figure' in block_type:
                caption = self._extract_image_caption(block, nested_content)
                footnote = self._extract_image_footnote(block, nested_content)
                extracted_text = normalize_text('\n'.join(x for x in [caption, footnote] if x))
                image_path = self._extract_image_path(block)

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
                md_image = self._build_image_markdown(caption, image_path, footnote)
                content_items.append(
                    {
                        'item_type': 'figure',
                        'level': None,
                        'content': md_image,
                        'bbox': self._block_bbox(block),
                        'page_number': page_number,
                        'order_index': order,
                    }
                )
                order += 1
                continue

            if 'equation' in block_type or 'formula' in block_type:
                # MinerU 的 formula/equation 块的 LaTeX 深层嵌套在 content 字典的 math_content 字段中
                block_content = block.get('content') or {}
                latex = ''
                math_type = ''
                if isinstance(block_content, dict):
                    # 精准提取 math_content 字段中的 LaTeX 代码
                    math_content = block_content.get('math_content') or ''
                    math_type = str(block_content.get('math_type') or block.get('math_type') or '').lower()
                    if isinstance(math_content, str) and math_content.strip():
                        latex = math_content.strip()
                    elif isinstance(math_content, dict):
                        latex = self._stringify_mineru_value(math_content)
                    elif isinstance(math_content, list):
                        latex = ''.join(str(x) for x in math_content if x)
                    else:
                        # 兜底：从整个 content 字典提取
                        latex = self._stringify_mineru_value(block_content)
                else:
                    latex = self._stringify_mineru_value(block_content)

                latex = self._wrap_latex_content(latex, math_type)
                if not latex:
                    continue

                content_items.append(
                    {
                        'item_type': 'formula',
                        'level': None,
                        'content': latex,
                        'bbox': self._block_bbox(block),
                        'page_number': page_number,
                        'order_index': order,
                    }
                )
                order += 1
                continue

            if block_type in ('list', 'index') or (
                isinstance(nested_content, dict) and nested_content.get('list_items')
            ):
                text = self._render_list_content(nested_content)
                if text:
                    content_items.append(
                        {
                            'item_type': 'paragraph',
                            'level': None,
                            'content': text,
                            'bbox': self._block_bbox(block),
                            'page_number': page_number,
                            'order_index': order,
                        }
                    )
                    order += 1
                continue

            block_content = block.get('content')
            if isinstance(block_content, dict):
                if 'paragraph_content' in block_content:
                    text = self._render_rich_content(block_content.get('paragraph_content'))
                elif 'title_content' in block_content:
                    text = self._render_rich_content(block_content.get('title_content'))
                    title_level = block_content.get('level') or block.get('level') or level
                    if text:
                        content_items.append(
                            {
                                'item_type': 'heading',
                                'level': self._to_int(title_level, default=1),
                                'content': text,
                                'bbox': self._block_bbox(block),
                                'page_number': page_number,
                                'order_index': order,
                            }
                        )
                        order += 1
                    continue
                elif block_content.get('list_items'):
                    text = self._render_list_content(block_content)
                else:
                    text = ''
            else:
                text = ''

            if not text:
                text = self._stringify_mineru_value(
                    block.get('text')
                    or block_content
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
                    'bbox': self._block_bbox(block),
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
                    'bbox': None,
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
                    'bbox': None,
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
                caption = normalize_text(image.group(1) or '')
                image_path = image.group(2) or None
                md_image = self._build_image_markdown(caption, image_path)
                figures_tables.append(
                    {
                        'type': 'figure',
                        'caption': caption or 'Figure extracted by MinerU',
                        'page_number': None,
                        'image_path': image_path,
                        'extracted_text': md_image,
                        'order_index': len(figures_tables),
                    }
                )
                content_items.append(
                    {
                        'item_type': 'figure',
                        'level': None,
                        'content': md_image,
                        'bbox': None,
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
                        'bbox': None,
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
    def _build_image_markdown(caption: str, image_path, footnote: str = '') -> str:
        """组装图片 Markdown：图片行 + 可见图题（与 MinerU 原生 .md 一致）。

        图题放在图片下方独立一行，而不是写在 alt 文本里（alt 在浏览器中不可见）。
        """
        cap = (caption or '').strip()
        note = (footnote or '').strip()
        path = str(image_path or '').strip()
        if path:
            path = path.replace('\\', '/')
            lines = [f'![]({path})']
            if cap:
                lines.append(cap)
            if note:
                lines.append(note)
            return '\n'.join(lines)
        return normalize_text('\n'.join(x for x in [cap, note] if x))

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
        """解析阶段从 MinerU 输出目录读取图片字节，供 pipeline 上传 MinIO。"""
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
                candidates = list(output_dir.rglob(Path(img_path).name))
                if candidates:
                    img_file = candidates[0]
                else:
                    missed += 1
                    logger.warning('Image file not found: %s (searched in %s)', img_path, output_dir)
                    continue

            try:
                normalized_key = str(img_path).replace('\\', '/')
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
            r'(?:keywords?|index\s+terms)\s*[:：]\s*(.+)',
            r'(?:关键词|关键字)\s*[:：]\s*(.+)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, markdown_text, flags=re.I):
                candidates.append(match.group(1))

        for idx, item in enumerate(content_items):
            text = normalize_text(str(item.get('content') or ''))
            if item.get('item_type') == 'heading' and re.search(
                r'keywords?|index\s+terms|关键词|关键字',
                text,
                flags=re.I,
            ):
                for nxt in content_items[idx + 1: idx + 4]:
                    if nxt.get('item_type') == 'heading':
                        break
                    if nxt.get('content'):
                        candidates.append(str(nxt.get('content')))
                        break

        joined = '；'.join(candidates)
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

        # ---------- 2.4 修复 MinerU 切割错误的行内定界符 ----------
        for item in cleaned_items:
            if item.get('item_type') not in ('paragraph', 'list', 'table'):
                continue
            content = item.get('content', '')
            if '$$' in content and '$' in content:
                item['content'] = re.sub(
                    r'(\$[^$\n]*?)\$\$(\\[a-zA-Z]+)',
                    r'\1$ $\2',
                    content,
                )

        # ---------- 2.5 公式升维：检测被 MinerU 误判为 paragraph 的 LaTeX 公式 ----------
        for item in cleaned_items:
            if item.get('item_type') not in ('paragraph', 'list'):
                continue

            content = item.get('content', '').strip()
            if not content:
                continue

            # MinerU 已输出完整 $$...$$ 包裹，只需升维并规范化 LaTeX
            if content.startswith('$$') and content.endswith('$$'):
                inner = self._normalize_latex_for_katex(content[2:-2])
                item['content'] = f'$$\n{inner}\n$$'
                item['item_type'] = 'formula'
                continue

            # 无 $$ 包裹但有 LaTeX 命令 → 补包裹后升维（跳过中英文混排 / 行内公式段落）
            if self._should_upgrade_paragraph_to_formula(content):
                content = self._ORPHAN_CLOSING_RE.sub('', content).strip()
                content = self._normalize_latex_for_katex(content)

                if content.count(r'\tag') > 1:
                    content = re.sub(r'(\\tag\{[^}]+\})\s*', r'\1 \\\\ \n', content)
                    content = re.sub(r' \\\\ \n$', '\n', content)
                    item['content'] = '$$\n\\begin{align}\n' + content + '\\end{align}\n$$'
                else:
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
                    if not final_items[-1].get('page_number') and item.get('page_number'):
                        final_items[-1]['page_number'] = item.get('page_number')
                    if not final_items[-1].get('bbox') and item.get('bbox'):
                        final_items[-1]['bbox'] = item.get('bbox')
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
            if value.get('list_items'):
                return self._render_list_content(value)
            if 'item_content' in value:
                return self._render_rich_content(value.get('item_content'))
            for key in ('math_content', 'text', 'content', 'html', 'caption'):
                if key in value:
                    return self._stringify_mineru_value(value.get(key))
            for key in (
                'page_header_content',
                'page_footer_content',
                'page_number_content',
                'title_content',
                'paragraph_content',
            ):
                if key in value:
                    return self._render_rich_content(value.get(key))
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
