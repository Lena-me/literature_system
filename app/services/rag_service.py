from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.integrations.embeddings.bge_embedding import BGEEmbedding
from app.integrations.embeddings.bge_reranker import BGEReranker
from app.integrations.milvus.client import MilvusChunkStore
from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.models import QASession, QAMessage, QAMessageSource, QASessionPaper, TextChunk
settings = get_settings()

class RAGService:
    def __init__(self) -> None:
        self.embedding = BGEEmbedding()
        self.reranker = BGEReranker()
        self.vdb = MilvusChunkStore()
        self.llm = OpenAICompatibleLLM()

    async def _add_message_sources(self, db: AsyncSession, message_id: int, ranked: list[dict]) -> None:
        """插入消息来源记录，自动过滤 Milvus 中已过期（MySQL 中不存在的）chunk_id"""
        chunk_ids = {c.get('chunk_id') for c in ranked if c.get('chunk_id')}
        valid_ids: set[int] = set()
        if chunk_ids:
            result = await db.execute(
                select(TextChunk.id).where(TextChunk.id.in_(chunk_ids))
            )
            valid_ids = {row[0] for row in result.fetchall()}
        for c in ranked:
            cid = c.get('chunk_id')
            db.add(QAMessageSource(
                message_id=message_id,
                chunk_id=cid if cid in valid_ids else None,
                paper_id=c.get('paper_id'),
                section_title=c.get('section_title'),
                page_number=c.get('page_number'),
                snippet=(c.get('text') or '')[:1000],
                similarity_score=float(c.get('rerank_score', c.get('score', 0))),
            ))

    async def ask(self, db: AsyncSession, user_id: int, question: str, paper_ids: list[int] | None, session_id: int | None, top_k: int | None) -> dict:
        session = await self._get_or_create_session(db, user_id, question, paper_ids, session_id)
        user_msg = QAMessage(session_id=session.id, role='user', content=question); db.add(user_msg); await db.flush()
        query_vector = self.embedding.encode_query(question)
        candidates = self.vdb.search(query_vector, paper_ids, top_k or settings.top_k)
        ranked = self.reranker.rerank(question, candidates, settings.rerank_top_n)
        context = '\n\n'.join([f"[来源{i+1} | paper_id={c['paper_id']} | page={c.get('page_number')}]\n{c.get('text','')}" for i, c in enumerate(ranked)])
        prompt = f"""请基于以下检索到的真实论文片段回答问题。必须给出可追溯依据；如果片段无法支持答案，明确说明无法从当前文献中确认。\n\n问题：{question}\n\n检索片段：\n{context}"""
        answer = await self.llm.async_chat([{'role':'system','content':'你是严谨的科研文献问答Agent，所有结论必须基于检索片段。'}, {'role':'user','content':prompt}], temperature=0.1)
        assistant_msg = QAMessage(session_id=session.id, role='assistant', content=answer); db.add(assistant_msg); await db.flush()
        await self._add_message_sources(db, assistant_msg.id, ranked)
        await db.commit()
        return {'session_id': session.id, 'answer': answer, 'sources': ranked}


    async def ask_stream(self, db: AsyncSession, user_id: int, question: str, paper_ids: list[int] | None, session_id: int | None, top_k: int | None):
        session = await self._get_or_create_session(db, user_id, question, paper_ids, session_id)
        user_msg = QAMessage(session_id=session.id, role='user', content=question); db.add(user_msg); await db.flush()
        query_vector = self.embedding.encode_query(question)
        candidates = self.vdb.search(query_vector, paper_ids, top_k or settings.top_k)
        ranked = self.reranker.rerank(question, candidates, settings.rerank_top_n)
        yield {'type': 'session', 'session_id': session.id}
        yield {'type': 'sources', 'sources': ranked}
        context = '\n\n'.join([f"[来源{i+1} | paper_id={c['paper_id']} | page={c.get('page_number')}]\n{c.get('text','')}" for i, c in enumerate(ranked)])
        prompt = f"""请基于以下检索到的真实论文片段回答问题。必须给出可追溯依据；如果片段无法支持答案，明确说明无法从当前文献中确认。\n\n问题：{question}\n\n检索片段：\n{context}"""
        answer_parts: list[str] = []
        async for piece in self.llm.stream_chat([{'role':'system','content':'你是严谨的科研文献问答Agent，所有结论必须基于检索片段。'}, {'role':'user','content':prompt}], temperature=0.1):
            answer_parts.append(piece)
            yield {'type': 'delta', 'content': piece}
        answer = ''.join(answer_parts)
        assistant_msg = QAMessage(session_id=session.id, role='assistant', content=answer); db.add(assistant_msg); await db.flush()
        await self._add_message_sources(db, assistant_msg.id, ranked)
        await db.commit()
        yield {'type': 'done', 'session_id': session.id, 'answer': answer}

    async def _get_or_create_session(self, db: AsyncSession, user_id: int, question: str, paper_ids: list[int] | None, session_id: int | None) -> QASession:
        if session_id:
            session = await db.get(QASession, session_id)
            if session and session.user_id == user_id:
                return session
        session = QASession(user_id=user_id, title=question[:80])
        db.add(session); await db.flush()
        for pid in paper_ids or []:
            db.add(QASessionPaper(session_id=session.id, paper_id=pid))
        await db.flush()
        return session
