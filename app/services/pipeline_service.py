from __future__ import annotations

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

        extracted = self._extract_info_with_llm(parsed)
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
    # LLM — 不持有 DB
    # ========================================================================

    def _extract_info_with_llm(self, parsed: dict) -> dict:
        joined = '\n'.join(
            [x.get('content', '') for x in parsed.get('content_items', [])]
        )[:16000]

        prompt = f"""你是科研文献结构化抽取Agent。请仅输出JSON，字段包括：
title, authors, abstract, keywords, research_question, method, experiment_data,
main_results, innovations, limitations, future_work。
不得编造，缺失则为空字符串或空数组。

论文内容：
{joined}"""

        try:
            text = self.llm.chat(
                [{'role': 'system', 'content': '你只输出可解析JSON。'}, {'role': 'user', 'content': prompt}],
                temperature=0.0,
                max_tokens=2500,
            )
        except Exception:
            return {}

        data = loads(text, default=None)
        if isinstance(data, dict):
            return data

        import json
        import re
        m = re.search(r'\{.*\}', text, flags=re.S)
        if not m:
            return {}
        try:
            parsed_data = json.loads(m.group(0))
            return parsed_data if isinstance(parsed_data, dict) else {}
        except Exception:
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

    # ========================================================================
    # 向量化 + Milvus
    # ========================================================================

    def _load_content_for_chunks(self, paper_id: int) -> list[dict]:
        with celery_db() as db:
            result = db.execute(
                select(ContentItem)
                .where(ContentItem.paper_id == paper_id)
                .order_by(ContentItem.order_index.asc())
            )
            return [
                {'section_id': x.id, 'content': x.content, 'page_number': x.page_number}
                for x in result.scalars().all()
            ]

    def _insert_text_chunks(self, paper_id: int, chunks: list[dict]) -> list[dict]:
        if not chunks:
            return []
        with celery_db() as db:
            db.execute(delete(TextChunk).where(TextChunk.paper_id == paper_id))
            rows: list[dict] = []
            for c in chunks:
                m = TextChunk(
                    paper_id=paper_id,
                    section_id=c.get('section_id'),
                    chunk_text=c['text'],
                    page_number=c.get('page_number'),
                    start_position=c.get('start_position', 0),
                    end_position=c.get('end_position', 0),
                    chunk_size=len(c['text']),
                    overlap_length=settings.chunk_overlap,
                    vector_dim=settings.milvus_vector_dim,
                    vectorization_status='pending',
                )
                db.add(m)
                rows.append({'model': m, 'chunk': c})
            db.flush()
            output = [
                {'chunk_id': item['model'].id, 'paper_id': paper_id,
                 'page_number': item['model'].page_number, 'section_title': '',
                 'text': item['model'].chunk_text}
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
        items = self._load_content_for_chunks(paper_id)
        chunks = semantic_chunks(items, settings.chunk_size, settings.chunk_overlap)
        texts = [c['text'] for c in chunks]
        vectors = self.embedding.encode_documents(texts) if texts else []

        db_rows = self._insert_text_chunks(paper_id, chunks)
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
