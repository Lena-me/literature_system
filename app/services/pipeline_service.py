from __future__ import annotations

import json
import logging
import re
from html import unescape
from pathlib import Path


import fitz
import httpx
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.mysql import celery_db
from app.integrations.document_parser.parser_factory import get_document_parser
from app.integrations.embeddings.bge_embedding import BGEEmbedding
from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.integrations.milvus.client import MilvusChunkStore
from app.integrations.object_storage.minio_storage import MinioStorage
from app.models import ContentItem, FiguresTable, Paper, PaperExtractedInfo, TextChunk
from app.utils.json_utils import dumps, loads
from app.utils.text_utils import semantic_chunks

settings = get_settings()
logger = logging.getLogger(__name__)


class PaperPipelineService:
    def __init__(self) -> None:
        self.storage = MinioStorage()
        self.parser = get_document_parser()
        self.embedding = BGEEmbedding()
        self.vdb = MilvusChunkStore()
        self.llm = OpenAICompatibleLLM() if settings.enable_llm_extract else None

    def parse_extract_vectorize(self, paper_id: int) -> None:
        logger.info('[paper=%s] Pipeline started', paper_id)
        paper = self._load_paper_snapshot(paper_id)
        self._set_paper_status(paper_id, 'parsing')

        logger.info('[paper=%s] Downloading PDF from MinIO...', paper_id)
        pdf_bytes = self.storage.get_pdf(paper['object_key'])
        logger.info('[paper=%s] PDF downloaded (%d bytes), parsing with %s...', paper_id, len(pdf_bytes), settings.document_parser)
        parsed = self.parser.parse(pdf_bytes, paper['original_filename'])
        logger.info('[paper=%s] Parsing done, %d content items, %d figures/tables', paper_id, len(parsed.get('content_items', [])), len(parsed.get('figures_tables', [])))

        # 将 MinerU 提取的图片上传到 MinIO，替换本地路径为可访问 URL
        self._upload_and_replace_images(parsed, paper_id)

        self._replace_parsed_content(paper_id, parsed)
        self._set_paper_status(paper_id, 'extracting')

        logger.info('[paper=%s] Extracting metadata...', paper_id)
        extracted = self._extract_info_hybrid(parsed, pdf_bytes)
        self._save_extracted_info(paper_id, parsed, extracted)

        self._set_paper_status(paper_id, 'vectorizing')
        logger.info('[paper=%s] Building vector index...', paper_id)
        self._build_vector_index(paper_id)
        self._set_paper_status(paper_id, 'completed')
        logger.info('[paper=%s] Pipeline completed', paper_id)


    def _load_paper_snapshot(self, paper_id: int) -> dict:
        with celery_db() as db:
            paper = db.get(Paper, paper_id)
            if not paper:
                raise ValueError(f'paper not found: {paper_id}')
            if not paper.object_key:
                raise ValueError(f'paper {paper_id} has no object_key')
            if paper.is_deleted:
                raise ValueError(f'paper {paper_id} has been deleted')
            return {
                'id': paper.id,
                'object_key': paper.object_key,
                'original_filename': paper.original_filename,
                'title': paper.title,
            }

    def _upload_and_replace_images(self, parsed: dict, paper_id: int) -> None:
        """将 MinerU 提取的图片上传到 MinIO，替换本地路径为永久公开 URL 存入数据库。"""
        image_data: dict[str, bytes] = parsed.pop('_image_data', {}) or {}
        if not image_data:
            logger.info('[paper=%s] No images to upload', paper_id)
            return

        # 上传并建立双映射：{原始路径: URL} + {文件名: URL}，用文件名做兜底匹配
        path_map: dict[str, str] = {}       # 原始路径 → URL
        basename_map: dict[str, str] = {}   # 文件名 → URL
        uploaded = 0

        for idx, (orig_path, img_bytes) in enumerate(image_data.items()):
            ext = Path(orig_path).suffix or '.png'
            object_key = f'papers/{paper_id}/images/{idx:03d}{ext}'
            try:
                content_type = 'image/jpeg' if ext.lower() in ('.jpg', '.jpeg') else 'image/png'
                self.storage.put_export(object_key, img_bytes, content_type)
                url = self.storage.export_public_url(object_key)
                # 主映射：原始路径（已标准化 \ → /）
                path_map[orig_path] = url
                # 兜底映射：仅用文件名匹配（适配绝对路径/相对路径不一致的情况）
                basename_map[Path(orig_path).name] = url
                logger.debug('[paper=%s] Image uploaded: %s -> %s, basename=%s', paper_id, object_key, url, Path(orig_path).name)
                uploaded += 1
            except Exception as e:
                logger.warning('[paper=%s] Failed to upload image %s: %s', paper_id, orig_path, e)

        if not path_map:
            logger.warning('[paper=%s] All image uploads failed', paper_id)
            return

        logger.info('[paper=%s] Uploaded %d/%d images to MinIO', paper_id, uploaded, len(image_data))

        # ── 替换 content_items 中的路径 ──
        replaced_content = 0
        for item in parsed.get('content_items', []):
            if item.get('item_type') == 'table':
                continue
            content = item.get('content', '')
            if not content:
                continue

            updated = self._replace_image_urls_in_text(content, path_map, basename_map)
            if updated != content:
                replaced_content += 1
            item['content'] = updated

        # ── 替换 figures_tables 中的路径（image_path + extracted_text）──
        replaced_ft = 0
        for ft in parsed.get('figures_tables', []):
            if ft.get('type') != 'figure':
                continue
            # 1) image_path 字段
            old_img = ft.get('image_path')
            if old_img:
                normalized_img = (old_img or '').replace('\\', '/')
                if normalized_img in path_map:
                    ft['image_path'] = path_map[normalized_img]
                    replaced_ft += 1
                else:
                    # 文件名兜底
                    name = Path(normalized_img).name
                    if name and name in basename_map:
                        ft['image_path'] = basename_map[name]
                        replaced_ft += 1

            # 2) extracted_text 中也可能有本地路径
            ext_text = ft.get('extracted_text', '')
            if ext_text:
                updated_text = self._replace_image_urls_in_text(ext_text, path_map, basename_map)
                if updated_text != ext_text:
                    ft['extracted_text'] = updated_text
                    replaced_ft += 1

        logger.info('[paper=%s] Replaced paths in %d content items + %d figure entries', paper_id, replaced_content, replaced_ft)

    @staticmethod
    def _replace_image_urls_in_text(text: str, path_map: dict[str, str], basename_map: dict[str, str]) -> str:
        """在文本中查找 Markdown 图片语法 ![...](xxx)，将 xxx 替换为 MinIO URL。
        支持两种匹配策略：1) 完整路径精确替换 2) 文件名兜底替换。"""
        def replace_match(m: re.Match) -> str:
            alt = m.group(1)
            url = m.group(2).replace('\\', '/')
            # 策略1：完整路径精确匹配
            if url in path_map:
                return f'![{alt}]({path_map[url]})'
            # 策略2：文件名兜底
            name = Path(url).name
            if name and name in basename_map:
                return f'![{alt}]({basename_map[name]})'
            return m.group(0)

        # 匹配 ![任意caption](任意path)，path 支持绝对路径、反斜杠、空格
        return re.sub(r'!\[(.*?)\]\((.*?)\)', replace_match, text)

    def _set_paper_status(self, paper_id: int, status: str) -> None:
        with celery_db() as db:
            paper = db.get(Paper, paper_id)
            if paper:
                paper.parse_status = status
            db.commit()

    def _truncate_text(self, text, max_length: int = 1048576) -> str:
        if text is None:
            return ''
        text = str(text)
        if len(text) > max_length:
            return text[:max_length] + '... [truncated]'
        return text

    @staticmethod
    def _normalize_content_item_type(value: object) -> str:
        raw = str(value or 'paragraph').strip().lower()
        aliases = {
            'text': 'paragraph',
            'para': 'paragraph',
            'section': 'heading',
            'title': 'heading',
            'equation': 'formula',
            'math': 'formula',
            'image': 'figure_caption',
            'figure': 'figure_caption',
            'caption': 'figure_caption',
            'ref': 'reference',
            'refs': 'reference',
            'bibliography': 'reference',
        }
        item_type = aliases.get(raw, raw)
        allowed = {
            'paragraph',
            'heading',
            'abstract',
            'table',
            'figure_caption',
            'formula',
            'list',
            'reference',
            'footnote',
        }
        return item_type if item_type in allowed else 'paragraph'

    @staticmethod
    def _reference_to_text(ref: object) -> str:
        if ref is None:
            return ''

        if isinstance(ref, dict):
            parts = []
            authors = ref.get('authors') or ref.get('author')
            year = ref.get('year') or ref.get('date')
            title = ref.get('title')
            venue = ref.get('venue') or ref.get('journal') or ref.get('booktitle')
            doi = ref.get('doi')
            raw = ref.get('raw') or ref.get('text') or ref.get('content')

            if authors:
                if isinstance(authors, (list, tuple)):
                    authors = ', '.join(str(x) for x in authors if x)
                parts.append(str(authors))
            if year:
                parts.append(str(year))
            if title:
                parts.append(str(title))
            if venue:
                parts.append(str(venue))
            if doi:
                parts.append(f'DOI: {doi}')

            if parts:
                return ' '.join(parts).strip()
            if raw:
                return str(raw).strip()
            return str(ref).strip()

        return str(ref).strip()

    def _replace_parsed_content(self, paper_id: int, parsed: dict) -> None:
        with celery_db() as db:
            paper = db.get(Paper, paper_id)
            if not paper:
                raise ValueError(f'paper not found: {paper_id}')

            db.execute(delete(TextChunk).where(TextChunk.paper_id == paper_id))
            db.execute(delete(FiguresTable).where(FiguresTable.paper_id == paper_id))
            db.execute(delete(ContentItem).where(ContentItem.paper_id == paper_id))

            max_order = 0
            saved_content_items = 0

            for idx, item in enumerate(parsed.get('content_items') or []):
                raw_order = item.get('order_index')
                try:
                    order_index = int(raw_order) if raw_order is not None else idx
                except Exception:
                    order_index = idx

                content = self._truncate_text(item.get('content', ''))
                if not str(content).strip():
                    continue

                db.add(ContentItem(
                    paper_id=paper_id,
                    item_type=self._normalize_content_item_type(item.get('item_type', 'paragraph')),
                    level=item.get('level'),
                    content=content,
                    page_number=item.get('page_number'),
                    order_index=order_index,
                ))
                saved_content_items += 1
                max_order = max(max_order, order_index + 1)

            saved_references = 0
            seen_refs: set[str] = set()
            for ref_index, ref in enumerate(parsed.get('references') or []):
                ref_text = ' '.join(self._reference_to_text(ref).split())
                if not ref_text:
                    continue
                dedup_key = ref_text[:300]
                if dedup_key in seen_refs:
                    continue
                seen_refs.add(dedup_key)

                db.add(ContentItem(
                    paper_id=paper_id,
                    item_type='reference',
                    level=None,
                    content=self._truncate_text(ref_text),
                    page_number=None,
                    order_index=max_order + ref_index,
                ))
                saved_references += 1

            for item in parsed.get('figures_tables') or []:
                db.add(FiguresTable(
                    paper_id=paper_id,
                    type=item.get('type', 'table'),
                    caption=self._truncate_text(item.get('caption')),
                    page_number=item.get('page_number'),
                    image_path=item.get('image_path'),
                    extracted_text=self._truncate_text(item.get('extracted_text')),
                    order_index=item.get('order_index', 0),
                ))

            meta = parsed.get('metadata') or {}
            paper.title = paper.title or meta.get('title') or paper.original_filename
            if meta.get('authors'):
                paper.authors = dumps(meta.get('authors'))
            if meta.get('keywords'):
                paper.keywords = dumps(meta.get('keywords'))

            db.commit()
            logger.info(
                '[paper=%s] Parsed content saved: %d content items, %d references',
                paper_id,
                saved_content_items,
                saved_references,
            )

    @staticmethod
    def _extract_pdf_embedded_metadata(pdf_bytes: bytes) -> dict:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype='pdf')
            meta = doc.metadata or {}
            doc.close()
            result: dict = {}
            title = (meta.get('title') or '').strip()
            if title and not title.lower().startswith(('microsoft', 'powerpoint')):
                result['title'] = title
            author_str = (meta.get('author') or '').strip()
            if author_str:
                result['authors'] = [a.strip() for a in re.split(r'[;,]', author_str) if a.strip()]
            return result
        except Exception:
            return {}

    @staticmethod
    def _find_doi(text: str) -> str | None:
        doi_match = re.search(r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', text, re.IGNORECASE)
        if doi_match:
            return doi_match.group(0).rstrip('.,;:')
        arxiv_match = re.search(
            r'(?:arxiv:\s*|arXiv:\s*|arxiv\.org/abs/)(\d{4}\.\d{4,5})',
            text,
            re.IGNORECASE,
        )
        if arxiv_match:
            return f'10.48550/arXiv.{arxiv_match.group(1)}'
        return None

    @staticmethod
    def _fetch_crossref_metadata(doi: str) -> dict:
        url = f'https://api.crossref.org/works/{doi}'
        try:
            resp = httpx.get(url, timeout=5.0)
            if resp.status_code != 200:
                return {}
            data = resp.json().get('message', {})
        except Exception:
            return {}

        authors = []
        for author in data.get('author', []):
            family = (author.get('family') or '').strip()
            given = (author.get('given') or '').strip()
            name = f'{family} {given}'.strip() or family or given
            if name:
                authors.append(name)

        pub = data.get('published-print') or data.get('published-online') or {}
        year = None
        date_parts = pub.get('date-parts', [[None]])
        if date_parts and date_parts[0] and date_parts[0][0] is not None:
            year = str(date_parts[0][0])

        return {
            'title': (data.get('title') or [None])[0],
            'authors': authors,
            'abstract': data.get('abstract'),
            'publication_year': year,
            'journal_conf': (data.get('container-title') or [None])[0],
        }

    def _extract_info_hybrid(self, parsed: dict, pdf_bytes: bytes) -> dict:
        meta = parsed.get('metadata') or {}
        result: dict = {
            'title': meta.get('title'),
            'authors': meta.get('authors') or [],
            'abstract': meta.get('abstract'),
            'keywords': meta.get('keywords') or [],
            'doi': meta.get('doi'),
            'publication_year': meta.get('publication_year'),
            'journal_conf': meta.get('journal_conf'),
        }

        pdf_meta = self._extract_pdf_embedded_metadata(pdf_bytes)
        result['title'] = result.get('title') or pdf_meta.get('title')
        result['authors'] = result.get('authors') or pdf_meta.get('authors') or []

        joined_for_doi = (
            parsed.get('markdown')
            or '\n'.join([x.get('content', '') for x in parsed.get('content_items', [])])
        )[:8000]
        doi = result.get('doi') or self._find_doi(joined_for_doi)
        if doi:
            result['doi'] = doi
            crossref = self._fetch_crossref_metadata(doi)
            if crossref:
                result['title'] = crossref.get('title') or result.get('title')
                result['authors'] = crossref.get('authors') or result.get('authors') or []
                result['abstract'] = crossref.get('abstract') or result.get('abstract')
                result['publication_year'] = crossref.get('publication_year') or result.get('publication_year')
                result['journal_conf'] = crossref.get('journal_conf') or result.get('journal_conf')

        llm_result = self._extract_info_with_llm(parsed) if settings.enable_llm_extract else {}
        supplement_fields = [
            'title',
            'authors',
            'abstract',
            'keywords',
            'doi',
            'publication_year',
            'journal_conf',
            'research_question',
            'method',
            'experiment_data',
            'main_results',
            'innovations',
            'limitations',
            'future_work',
        ]

        for key in supplement_fields:
            value = llm_result.get(key)
            if value in (None, '', []):
                continue
            if key == 'title':
                if not result.get(key):
                    result[key] = value
                continue

            if key == 'authors':
                cleaned_authors = self._clean_author_list(value)
                current_authors = self._clean_author_list(result.get('authors') or [])

                if cleaned_authors:
                    if (
                        not current_authors
                        or self._authors_look_bad(current_authors)
                        or len(cleaned_authors) > len(current_authors)
                    ):
                        result[key] = cleaned_authors
                continue

            if key in {'abstract', 'keywords', 'doi', 'publication_year', 'journal_conf'}:
                if not result.get(key):
                    result[key] = value
                continue
            result[key] = value

        return result

    def _clean_author_list(self, authors) -> list[str]:
        if not authors:
            return []

        if isinstance(authors, str):
            raw_items = re.split(r'\s*,\s*|\s+and\s+|；|;|、', authors)
        elif isinstance(authors, list):
            raw_items = authors
        else:
            return []

        cleaned = []
        seen = set()

        for item in raw_items:
            if not item:
                continue

            name = str(item)
            name = unescape(name)
            name = re.sub(r'<[^>]+>', ' ', name)
            name = re.sub(r'\$[^$]*\$', ' ', name)
            name = re.sub(r'\[[^\]]*\]', ' ', name)
            name = re.sub(r'\([^)]*\)', ' ', name)
            name = re.sub(r'\d+', ' ', name)
            name = re.sub(r'[*†‡§]+', ' ', name)
            name = re.sub(r'\s+', ' ', name).strip(' ,;；、')

            if not name:
                continue

            if re.search(
                r'\b(university|institute|department|school|college|laboratory|abstract|keywords|gmail|email|@)\b',
                name,
                flags=re.I,
            ):
                continue

            if len(name) < 2 or len(name) > 80:
                continue

            key = name.lower()
            if key not in seen:
                cleaned.append(name)
                seen.add(key)

            if len(cleaned) >= 30:
                break

        return cleaned

    def _authors_look_bad(self, authors: list[str]) -> bool:
        if not authors:
            return True

        joined = ' '.join(authors)
        lowered = joined.lower()
        if any(token in lowered for token in ['<sup', '</sup', '@', 'university', 'department', 'institute']):
            return True

        if len(authors) == 1 and len(authors[0].split()) <= 2:
            return True

        return False

    def _is_valid_doi(self, doi: str) -> bool:
        doi = doi.strip()
        if not doi:
            return False

        bad_tokens = ['nnnn', 'xxxx', 'xxxxx', 'todo', 'placeholder']
        if any(token in doi.lower() for token in bad_tokens):
            return False

        return bool(re.match(r'^10\.\d{4,9}/\S+$', doi, flags=re.I))

    @staticmethod
    def _clean_json_output(raw_response: str) -> str:
        cleaned = raw_response.strip()
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\n?\s*```\s*$', '', cleaned)
        return cleaned.strip()

    def _extract_info_with_llm(self, parsed: dict) -> dict:
        joined_source = parsed.get('markdown') or '\n'.join(
            [x.get('content', '') for x in parsed.get('content_items', [])]
        )
        joined = joined_source[:16000]

        prompt = f"""你是一个严谨的学术文献信息抽取系统。请从提供的 PDF 文本中提取结构化元数据。

严格规则：
1. 只输出标准 JSON，不要附带解释、问候语或 Markdown 代码块。
2. 无法确定的信息保留字段，值设为 null 或 []。
3. authors 只提取人名，不要带职称、学位或单位信息。
4. keywords 优先从 Keywords、Index Terms、关键词、关键字 后面的显式内容提取；没有显式关键词时，再根据标题、摘要和引言归纳 3-8 个学术术语。
5. doi 优先从原文中提取 10.xxxx/xxxxx 或 arXiv 编号；没有则为 null。
6. publication_year 必须是整数年份；无法确定则为 null。
7. 输出 JSON 必须包含以下全部字段，不得遗漏。

JSON 示例：
{{
    "title": "基于边缘信息增强的超声图像去噪算法研究",
    "authors": ["蒋温平"],
    "abstract": "本文针对超声图像中存在的散斑噪声问题，提出了一种基于边缘信息增强的去噪算法...",
    "keywords": ["超声图像", "去噪", "边缘信息增强", "深度学习", "Canny算子"],
    "research_question": "如何在去除超声图像噪声的同时有效保留边缘细节信息",
    "method": "提出基于边缘信息增强的深度学习去噪框架，结合Canny边缘检测与注意力机制",
    "experiment_data": "在公开数据集和临床超声图像上进行实验验证",
    "main_results": "相比现有方法PSNR提升2.3dB，边缘保持指数提升5.7%",
    "innovations": "将边缘检测与去噪网络深度融合，提出边缘引导的损失函数",
    "limitations": "对极低信噪比图像处理效果仍有提升空间",
    "future_work": "将该方法扩展到3D超声图像和实时临床场景",
    "doi": null,
    "publication_year": null,
    "journal_conf": "湖南大学硕士学位论文"
}}

待抽取文本：
<text>
{joined}
</text>"""

        try:
            if self.llm is None:
                return {}
            text = self.llm.chat(
                [{'role': 'system', 'content': '你只输出可解析 JSON。'},
                 {'role': 'user', 'content': prompt}],
                temperature=0.0,
                max_tokens=3000,
            )
        except Exception:
            return {}

        clean = self._clean_json_output(text)
        data = loads(clean, default=None)
        if isinstance(data, dict):
            return data

        match = re.search(r'\{.*\}', clean, flags=re.S)
        if match:
            try:
                parsed_data = json.loads(match.group(0))
                if isinstance(parsed_data, dict):
                    return parsed_data
            except Exception:
                pass

        print(f'[LLM抽取失败] 原始响应（前500字符）: {text[:500]}')
        return {}

    def _to_db_text(self, value) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, (list, dict, tuple, set)):
            return dumps(value)
        return str(value)

    def _to_title_text(self, value) -> str | None:
        text = self._to_db_text(value)
        if not text:
            return None
        return text[:500]

    def _save_extracted_info(self, paper_id: int, parsed: dict, extracted: dict) -> None:
        with celery_db() as db:
            paper = db.get(Paper, paper_id)
            if not paper:
                raise ValueError(f'paper not found: {paper_id}')

            old = db.execute(
                select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id == paper_id)
            ).scalar_one_or_none()
            if old:
                db.delete(old)
                db.flush()

            meta = parsed.get('metadata') or {}
            extracted = extracted or {}
            title = (
                extracted.get('title')
                or meta.get('title')
                or paper.title
                or paper.original_filename
            )
            raw_authors = (
                extracted.get('authors')
                if extracted.get('authors') not in (None, '', [])
                else (meta.get('authors') or [])
            )
            authors = self._clean_author_list(raw_authors)
            keywords = (
                extracted.get('keywords')
                if extracted.get('keywords') not in (None, '', [])
                else (meta.get('keywords') or [])
            )

            info = PaperExtractedInfo(
                paper_id=paper_id,
                title=self._to_title_text(title),
                authors=self._to_db_text(authors),
                abstract=self._to_db_text(extracted.get('abstract') or meta.get('abstract')),
                keywords=self._to_db_text(keywords),
                research_question=self._to_db_text(extracted.get('research_question')),
                method=self._to_db_text(extracted.get('method')),
                experiment_data=self._to_db_text(extracted.get('experiment_data')),
                main_results=self._to_db_text(extracted.get('main_results')),
                innovations=self._to_db_text(extracted.get('innovations')),
                limitations=self._to_db_text(extracted.get('limitations')),
                future_work=self._to_db_text(extracted.get('future_work')),
            )
            db.add(info)

            paper.title = info.title or paper.title
            if authors:
                paper.authors = dumps(authors)
            elif info.authors not in (None, '', '[]'):
                paper.authors = info.authors
            if info.keywords not in (None, '', '[]'):
                paper.keywords = info.keywords

            doi = extracted.get('doi') or meta.get('doi')
            if doi and self._is_valid_doi(str(doi)):
                paper.doi = str(doi)[:100]

            publication_year = extracted.get('publication_year') or meta.get('publication_year')
            if publication_year:
                try:
                    paper.publication_year = int(str(publication_year)[:4])
                except Exception:
                    pass

            journal_conf = extracted.get('journal_conf') or meta.get('journal_conf')
            if journal_conf:
                paper.journal_conf = str(journal_conf)[:300]

            db.commit()

    def _build_context_prefix(self, paper_id: int) -> str:
        with celery_db() as db:
            info = db.execute(
                select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id == paper_id)
            ).scalar_one_or_none()
            paper = db.get(Paper, paper_id)

        parts: list[str] = []
        title = (info.title if info else None) or (paper.title if paper else None) or ''
        if title:
            parts.append(f'[文献：{title.strip()[:200]}]')

        if info:
            method = info.method
            if method:
                method_str = ''
                try:
                    parsed = loads(method)
                    if isinstance(parsed, list):
                        method_str = '、'.join([str(m).strip()[:80] for m in parsed[:3] if m])
                    elif isinstance(parsed, str) and parsed.strip():
                        method_str = parsed.strip()[:120]
                except Exception:
                    if isinstance(method, str) and method.strip():
                        method_str = method.strip()[:120]
                if method_str:
                    parts.append(f'[核心方法：{method_str}]')

        return '\n'.join(parts) + '\n' if parts else ''

    def _load_content_for_chunks(self, paper_id: int) -> list[dict]:
        with celery_db() as db:
            result = db.execute(
                select(ContentItem)
                .where(ContentItem.paper_id == paper_id)
                .order_by(ContentItem.order_index.asc())
            )
            items = result.scalars().all()

        current_section_title = ''
        section_map: dict[int, str] = {}
        for item in items:
            if item.item_type == 'heading':
                current_section_title = (item.content or '')[:200]
            section_map[item.id] = current_section_title

        return [
            {
                'section_id': x.id,
                'content': x.content,
                'page_number': x.page_number,
                'section_title': section_map.get(x.id, ''),
            }
            for x in items
        ]

    def _insert_text_chunks(self, paper_id: int, chunks: list[dict], context_prefix: str = '') -> list[dict]:
        if not chunks:
            return []
        with celery_db() as db:
            db.execute(delete(TextChunk).where(TextChunk.paper_id == paper_id))
            rows: list[dict] = []
            for chunk in chunks:
                raw_text = chunk['text']
                model = TextChunk(
                    paper_id=paper_id,
                    section_id=chunk.get('section_id'),
                    chunk_text=raw_text,
                    page_number=chunk.get('page_number'),
                    start_position=chunk.get('start_position', 0),
                    end_position=chunk.get('end_position', 0),
                    chunk_size=len(raw_text),
                    overlap_length=settings.chunk_overlap,
                    vector_dim=settings.milvus_vector_dim,
                    vectorization_status='pending',
                )
                db.add(model)
                rows.append({'model': model, 'chunk': chunk})
            db.flush()

            output = [
                {
                    'chunk_id': item['model'].id,
                    'paper_id': paper_id,
                    'page_number': item['model'].page_number,
                    'section_title': (item['chunk'].get('section_title') or '')[:300],
                    'text': ((context_prefix or '') + item['model'].chunk_text)[:6000],
                }
                for item in rows
            ]
            db.commit()
            return output

    def _update_chunk_vector_ids(self, chunk_ids: list[int], vector_ids: list[str]) -> None:
        if not chunk_ids or not vector_ids:
            return
        with celery_db() as db:
            for chunk_id, vector_id in zip(chunk_ids, vector_ids, strict=False):
                chunk = db.get(TextChunk, chunk_id)
                if chunk:
                    chunk.vector_id_in_vdb = vector_id
                    chunk.vectorization_status = 'completed'
            db.commit()

    def _mark_chunks_failed(self, chunk_ids: list[int], error: str) -> None:
        if not chunk_ids:
            return
        with celery_db() as db:
            for chunk_id in chunk_ids:
                chunk = db.get(TextChunk, chunk_id)
                if chunk:
                    chunk.vectorization_status = 'failed'
            db.commit()

    def _build_vector_index(self, paper_id: int) -> None:
        context_prefix = self._build_context_prefix(paper_id)
        items = self._load_content_for_chunks(paper_id)
        chunks = semantic_chunks(items, settings.chunk_size, settings.chunk_overlap)
        texts = [(context_prefix or '') + chunk['text'] for chunk in chunks]
        vectors = self.embedding.encode_documents(texts) if texts else []

        db_rows = self._insert_text_chunks(paper_id, chunks, context_prefix)
        if not db_rows or not vectors:
            return

        chunk_ids = [int(row['chunk_id']) for row in db_rows]
        milvus_rows = [{**row, 'embedding': vector} for row, vector in zip(db_rows, vectors, strict=False)]

        try:
            vector_ids = self.vdb.insert_chunks(milvus_rows)
        except Exception as exc:
            self._mark_chunks_failed(chunk_ids, f'{type(exc).__name__}: {str(exc)[:500]}')
            raise

        self._update_chunk_vector_ids(chunk_ids, vector_ids)
