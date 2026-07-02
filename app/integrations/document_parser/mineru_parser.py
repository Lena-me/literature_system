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
                body = self._stringify_mineru_value(
                    block.get('table_body') or block.get('html') or block.get('content') or block.get('text') or ''
                )
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
                if extracted_text:
                    content_items.append(
                        {
                            'item_type': 'figure_caption',
                            'level': None,
                            'content': extracted_text,
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
                        'item_type': 'paragraph',
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
        text = re.sub(r'\d+|[*†‡§]|\([^)]*\)', ' ', text)

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
        """
        对 MinerU 提取的初步数据进行后置清洗：剔除目录、修复标题降维、合并断行与引用
        """
        cleaned_items = []

        for item in items:
            # 仅处理文本相关的 block
            if item.get('item_type') not in ('paragraph', 'heading', 'list'):
                cleaned_items.append(item)
                continue

            text = str(item.get('content', '')).strip()
            if not text:
                continue

            # ==========================================
            # 1. 剔除目录 (TOC 污染清洗)
            # ==========================================
            if re.search(r'(?:\.{3,}|…{2,})\s*\d+$', text):
                continue
            if re.match(r'^(目录|Contents?|图目录|表目录)$', text, re.I):
                continue

            # ==========================================
            # 2. 封面及声明页碎片清洗
            # ==========================================
            text_no_space = text.replace(' ', '')
            if len(text_no_space) < 30 and re.match(
                    r'^(分类号|UDC|密级|学校代码|学号|指导教师|专业名称|学位类别|作者姓名|学院|答辩委员会|答辩日期|原创性声明|授权使用说明)',
                    text_no_space):
                continue

            if len(text) < 15 and not re.search(r'[。！？：:;.!?]$', text) and (
                    '学位' in text or text in ['公开', '保密', '内部']):
                continue

            # ==========================================
            # 3. 标题强升维
            # ==========================================
            if item.get('item_type') in ('paragraph', 'list') and len(text) < 100 and not re.search(r'[。！？;.!?]$',
                                                                                                    text):
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

        # ==========================================
        # 4. 硬回车断行与引用割裂合并
        # ==========================================
        final_items = []
        for item in cleaned_items:
            curr_type = item.get('item_type')

            # 放宽合并条件：只要上一项和当前项是段落或“假列表”，就允许考察合并
            if final_items and curr_type in ('paragraph', 'list') and final_items[-1].get('item_type') in (
            'paragraph', 'list'):
                prev_text = final_items[-1]['content'].strip()
                curr_text = item['content'].strip()

                # 特征判定 1：前一段结尾没有句子终结符（兼容了结尾带有右括号、右引号的复杂情况）
                ends_without_period = not re.search(r'[。！？：:;.!?]["”’\'\)\]）】]?$', prev_text)

                # 特征判定 2：当前段落以引用标记开头 (如 [20], [1, 2-4])
                starts_with_citation = bool(re.match(r'^\[\s*\d+\s*(?:[,\-]\s*\d+\s*)*\]', curr_text))

                # 特征判定 3：当前段落完全是一个独立的引用标记 (如 "[20]" 或 "[20]。")
                is_standalone_citation = bool(re.match(r'^\[\s*\d+\s*(?:[,\-]\s*\d+\s*)*\][。！？.!?]?$', curr_text))

                # 特征判定 4：当前段落以小写字母开头，明显是半句话
                starts_with_lowercase = bool(re.match(r'^[a-z]', curr_text))

                should_merge = False

                if ends_without_period:
                    should_merge = True
                elif starts_with_citation or is_standalone_citation:
                    # 只要开头是引用，无视前文标点，强制吸附过来！
                    should_merge = True
                elif starts_with_lowercase:
                    should_merge = True

                if should_merge:
                    # 将误识别为 list 的情况强行纠正回 paragraph
                    final_items[-1]['item_type'] = 'paragraph'

                    # 拼接逻辑：如果是中英混排，自动补全空格
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
