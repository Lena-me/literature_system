from __future__ import annotations

import re

import fitz  # PyMuPDF — PDF 内嵌元数据提取
import httpx

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.mysql import celery_db
from app.integrations.document_parser.grobid_parser import GrobidPyMuPDFParser
from app.integrations.embeddings.bge_embedding import BGEEmbedding
from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.integrations.milvus.client import MilvusChunkStore
from app.integrations.object_storage.minio_storage import MinioStorage
from app.models import ContentItem, FiguresTable, Paper, PaperExtractedInfo, TextChunk
from app.utils.json_utils import dumps, loads
from app.utils.text_utils import semantic_chunks

settings = get_settings()


class PaperPipelineService:
    def __init__(self) -> None:
        self.storage = MinioStorage()
        self.parser = GrobidPyMuPDFParser()
        self.embedding = BGEEmbedding()
        self.vdb = MilvusChunkStore()
        self.llm = OpenAICompatibleLLM()

    # ========================================================================
    # Celery 同步入口（不再需要 asyncio.run）
    # ========================================================================

    def parse_extract_vectorize(self, paper_id: int) -> None:
        paper = self._load_paper_snapshot(paper_id)
        self._set_paper_status(paper_id, 'parsing')

        pdf_bytes = self.storage.get_pdf(paper['object_key'])
        parsed = self.parser.parse(pdf_bytes, paper['original_filename'])

        self._replace_parsed_content(paper_id, parsed)
        self._set_paper_status(paper_id, 'extracting')

        extracted = self._extract_info_hybrid(parsed, pdf_bytes)
        self._save_extracted_info(paper_id, parsed, extracted)

        self._set_paper_status(paper_id, 'vectorizing')
        self._build_vector_index(paper_id)
        self._set_paper_status(paper_id, 'completed')

    # ========================================================================
    # DB helpers — 每步独立短事务
    # ========================================================================

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

    def _set_paper_status(self, paper_id: int, status: str) -> None:
        with celery_db() as db:
            paper = db.get(Paper, paper_id)
            if paper:
                paper.parse_status = status
            db.commit()

    def _replace_parsed_content(self, paper_id: int, parsed: dict) -> None:
        with celery_db() as db:
            paper = db.get(Paper, paper_id)
            if not paper:
                raise ValueError(f'paper not found: {paper_id}')

            db.execute(delete(TextChunk).where(TextChunk.paper_id == paper_id))
            db.execute(delete(FiguresTable).where(FiguresTable.paper_id == paper_id))
            db.execute(delete(ContentItem).where(ContentItem.paper_id == paper_id))

            for item in parsed.get('content_items') or []:
                db.add(ContentItem(
                    paper_id=paper_id,
                    item_type=item.get('item_type', 'paragraph'),
                    level=item.get('level'),
                    content=item.get('content', ''),
                    page_number=item.get('page_number'),
                    order_index=item.get('order_index', 0),
                ))

            for item in parsed.get('figures_tables') or []:
                db.add(FiguresTable(
                    paper_id=paper_id,
                    type=item.get('type', 'table'),
                    caption=item.get('caption'),
                    page_number=item.get('page_number'),
                    extracted_text=item.get('extracted_text'),
                    order_index=item.get('order_index', 0),
                ))

            meta = parsed.get('metadata') or {}
            paper.title = paper.title or meta.get('title') or paper.original_filename
            paper.authors = dumps(meta.get('authors') or [])
            paper.keywords = dumps(meta.get('keywords') or [])

            db.commit()

    # ========================================================================
    # 混合提取：PDF元数据 → DOI/Crossref → LLM 三层递进
    # ========================================================================

    @staticmethod
    def _extract_pdf_embedded_metadata(pdf_bytes: bytes) -> dict:
        """从 PDF 二进制读取内嵌元数据（秒级，零网络成本）"""
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
                # PyMuPDF author 可能是 "Wang, Fangyijie; Li, Ming" 格式
                authors = [a.strip() for a in re.split(r'[;,]', author_str) if a.strip()]
                result['authors'] = authors
            return result
        except Exception:
            return {}

    @staticmethod
    def _find_doi(text: str) -> str | None:
        """从文本中正则提取 DOI（优先）或 arXiv ID"""
        # 标准 DOI 格式：10.XXXX/...
        doi_match = re.search(r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', text, re.IGNORECASE)
        if doi_match:
            return doi_match.group(0).rstrip('.,;:')
        # arXiv ID 格式：arXiv:XXXX.XXXXX 或 arxiv.org/abs/XXXX.XXXXX
        arxiv_match = re.search(
            r'(?:arxiv:\s*|arXiv:\s*|arxiv\.org/abs/)(\d{4}\.\d{4,5})',
            text, re.IGNORECASE,
        )
        if arxiv_match:
            return f'10.48550/arXiv.{arxiv_match.group(1)}'
        return None

    @staticmethod
    def _fetch_crossref_metadata(doi: str) -> dict:
        """通过 Crossref API 获取文献的权威元数据（Zotero同款）"""
        url = f'https://api.crossref.org/works/{doi}'
        try:
            resp = httpx.get(url, timeout=5.0)
            if resp.status_code != 200:
                return {}
            data = resp.json().get('message', {})
        except Exception:
            return {}

        authors = []
        for a in data.get('author', []):
            family = (a.get('family') or '').strip()
            given = (a.get('given') or '').strip()
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
        """
        三层递进混合提取：
        第0层 — GROBID metadata（已解析）
        第1层 — PDF 内嵌元数据（PyMuPDF，秒级零成本）
        第2层 — DOI → Crossref API（学术权威来源，Zotero同款）
        第3层 — LLM Few-Shot 兜底（仅在前3层无法获取关键字段时启用）
        """

        # ── 第0层：GROBID 已提取的 metadata ──
        grobid_meta = parsed.get('metadata') or {}
        result: dict = {
            'title': grobid_meta.get('title'),
            'authors': grobid_meta.get('authors') or [],
            'abstract': grobid_meta.get('abstract'),
            'keywords': grobid_meta.get('keywords') or [],
        }

        # ── 第1层：PDF 内嵌元数据 ──
        pdf_meta = self._extract_pdf_embedded_metadata(pdf_bytes)
        result['title'] = result['title'] or pdf_meta.get('title')
        result['authors'] = result['authors'] or pdf_meta.get('authors') or []

        # ── 第2层：DOI → Crossref API ──
        # 扫描前5000字符查找 DOI
        joined = '\n'.join(
            [x.get('content', '') for x in parsed.get('content_items', [])]
        )[:5000]
        doi = self._find_doi(joined)
        if doi:
            crossref = self._fetch_crossref_metadata(doi)
            if crossref:
                result['title'] = crossref.get('title') or result['title']
                result['authors'] = crossref.get('authors') or result['authors']
                result['abstract'] = crossref.get('abstract') or result['abstract']
                result['publication_year'] = crossref.get('publication_year')
                result['journal_conf'] = crossref.get('journal_conf')

        # ── 第3层：LLM 兜底（仅当关键字段仍缺失时）──
        missing_critical = not result.get('title') or not result.get('authors')
        if missing_critical:
            llm_result = self._extract_info_with_llm(parsed)
            for key in llm_result:
                if not result.get(key):
                    result[key] = llm_result[key]
        else:
            # 关键字段已有，仍用 LLM 补充深度分析字段
            llm_result = self._extract_info_with_llm(parsed)
            deep_fields = [
                'research_question', 'method', 'experiment_data',
                'main_results', 'innovations', 'limitations', 'future_work',
            ]
            for key in deep_fields:
                if key in llm_result and llm_result[key]:
                    result[key] = llm_result[key]

        return result

    # ========================================================================
    # LLM — 不持有 DB
    # ========================================================================

    @staticmethod
    def _clean_json_output(raw_response: str) -> str:
        """剥离大模型可能附加的 Markdown 代码块标记，确保纯净 JSON"""
        cleaned = raw_response.strip()
        # 移除 ```json ... ``` 或 ``` ... ``` 包裹
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\n?\s*```\s*$', '', cleaned)
        return cleaned.strip()

    def _extract_info_with_llm(self, parsed: dict) -> dict:
        # 扩大上下文窗口至 12000 字符，确保覆盖中英文摘要和引言
        joined = '\n'.join(
            [x.get('content', '') for x in parsed.get('content_items', [])]
        )[:12000]

        prompt = f"""你是一个严谨的学术文献信息抽取系统。你的唯一任务是从提供的 PDF 文本中提取结构化元数据。

【严格规则】
1. 只输出标准的 JSON 格式，绝不允许附带任何解释性文字、问候语或 Markdown 格式符号（禁止 ```json 包裹）。
2. 遇到无法确定的信息，必须保留该字段，但将值设为 null（字符串类型）或 []（数组类型）。
3. 作者列表(authors)只提取人名，不要带职称、学位或单位信息。
4. 关键词(keywords)尽量提取学术术语。如果是中文论文，优先提取中文关键词。
5. 你输出的 JSON 必须包含以下全部字段，不得遗漏任何一个。

【JSON 字段定义与示例】
{{
    "title": "基于边缘信息增强的超声图像去噪算法研究",
    "authors": ["蒋温平"],
    "abstract": "本文针对超声图像中存在的散斑噪声问题，提出了一种基于边缘信息增强的去噪算法...",
    "keywords": ["超声图像", "去噪", "边缘信息增强", "深度学习", "Canny算子"],
    "research_question": "如何在去除超声图像噪声的同时有效保留边缘细节信息",
    "method": "提出基于边缘信息增强的深度学习去噪框架，结合Canny边缘检测与注意力机制",
    "experiment_data": "在XXX公开数据集和临床超声图像上进行实验验证",
    "main_results": "相比现有方法PSNR提升2.3dB，边缘保持指数提升5.7%",
    "innovations": "首次将边缘检测与去噪网络深度融合，提出边缘引导的损失函数",
    "limitations": "对极度低信噪比图像处理效果仍有提升空间",
    "future_work": "将该方法扩展到3D超声图像和实时临床场景",
    "publication_year": null,
    "journal_conf": "湖南大学硕士学位论文"
}}

请对以下文本进行抽取：
<text>
{joined}
</text>"""

        try:
            text = self.llm.chat(
                [{'role': 'system', 'content': '你只输出可解析JSON。'},
                 {'role': 'user', 'content': prompt}],
                temperature=0.0,
                max_tokens=3000,
            )
        except Exception:
            return {}

        # 第一层：直接解析
        clean = self._clean_json_output(text)
        data = loads(clean, default=None)
        if isinstance(data, dict):
            return data

        # 第二层：正则兜底提取 JSON 对象
        import json
        m = re.search(r'\{.*\}', clean, flags=re.S)
        if m:
            try:
                parsed_data = json.loads(m.group(0))
                if isinstance(parsed_data, dict):
                    return parsed_data
            except Exception:
                pass

        # 最终兜底：打印原始响应以便调试
        print(f'[LLM抽取失败] 原始响应（前500字符）: {text[:500]}')
        return {}

    # ========================================================================
    # 结构化信息落库
    # ========================================================================

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
            authors = (
                extracted.get('authors')
                if extracted.get('authors') not in (None, '')
                else (meta.get('authors') or [])
            )
            keywords = (
                extracted.get('keywords')
                if extracted.get('keywords') not in (None, '')
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
            paper.authors = info.authors
            paper.keywords = info.keywords
            db.commit()

    def _build_context_prefix(self, paper_id: int) -> str:
        """从已提取的结构化信息构建元数据上下文前缀，注入到每个 chunk 用于提升检索质量"""
        with celery_db() as db:
            info = db.execute(
                select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id == paper_id)
            ).scalar_one_or_none()
            paper = db.get(Paper, paper_id)

        parts: list[str] = []

        # 1. 文献标题（核心锚点）
        title = (info.title if info else None) or (paper.title if paper else None) or ''
        if title:
            parts.append(f'[文献：{title.strip()[:200]}]')

        # 2. 核心方法 / 技术（提升"该模型"、"该方法"等指代消解）
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

    # ========================================================================
    # 向量化 + Milvus
    # ========================================================================

    def _load_content_for_chunks(self, paper_id: int) -> list[dict]:
        """加载 ContentItem 列表，同时为每个段落找到最近的章节标题"""
        with celery_db() as db:
            result = db.execute(
                select(ContentItem)
                .where(ContentItem.paper_id == paper_id)
                .order_by(ContentItem.order_index.asc())
            )
            items = result.scalars().all()

        # 构建 section_title 映射：每个段落继承其之前最近的 heading
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
        """
        MySQL 存储原始文本（不含上下文前缀），供前端展示。
        Milvus 存储富文本（含上下文前缀 + section_title），供向量检索。
        """
        if not chunks:
            return []
        with celery_db() as db:
            db.execute(delete(TextChunk).where(TextChunk.paper_id == paper_id))
            rows: list[dict] = []
            for c in chunks:
                raw_text = c['text']
                m = TextChunk(
                    paper_id=paper_id,
                    section_id=c.get('section_id'),
                    chunk_text=raw_text,              # MySQL 存原始文本
                    page_number=c.get('page_number'),
                    start_position=c.get('start_position', 0),
                    end_position=c.get('end_position', 0),
                    chunk_size=len(raw_text),
                    overlap_length=settings.chunk_overlap,
                    vector_dim=settings.milvus_vector_dim,
                    vectorization_status='pending',
                )
                db.add(m)
                rows.append({'model': m, 'chunk': c})
            db.flush()

            # 构建 Milvus 写入行：text 字段使用富文本（上下文前缀 + 原始文本）
            # section_title 从 chunk 元数据中获取（最近的章节标题）
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
        # 1. 构建元数据上下文前缀（文献标题 + 核心方法）
        context_prefix = self._build_context_prefix(paper_id)

        # 2. 加载 ContentItem（含 section_title），按语义边界分块
        items = self._load_content_for_chunks(paper_id)
        chunks = semantic_chunks(items, settings.chunk_size, settings.chunk_overlap)

        # 3. 向量化：使用富文本（上下文前缀 + 原始 chunk），提升语义检索质量
        texts = [(context_prefix or '') + c['text'] for c in chunks]
        vectors = self.embedding.encode_documents(texts) if texts else []

        # 4. 双写：MySQL 存原始文本，Milvus 存富文本（含上下文前缀）
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
