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
        prompt = f"""请基于以下检索到的真实论文片段回答问题。

【重要引用规则】
- 必须在句末标注对应片段的序号，格式为 [1]、[2]。
- 严禁照抄检索片段中原本自带的参考文献编号（如 [40], [41] 等），那些编号与本系统无关。
- 如果检索片段无法支撑答案，请明确说明"当前挂载的文献中未找到相关信息"。
- 引用示例："...该方法在小目标检测上提升了12%的mAP[1]。"

问题：{question}

检索片段：
{context}"""

        system_prompt = """你是严谨的科研文献问答Agent。你必须：
1. 所有结论严格基于检索片段，不得编造。
2. 引用时使用 [1]、[2] 格式（对应片段序号），句末标注。
3. 绝对禁止在回答中出现检索片段里的原始参考文献编号（如 [40]、[41]）。"""
        answer = await self.llm.async_chat([{'role':'system','content': system_prompt}, {'role':'user','content':prompt}], temperature=0.1)
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
        prompt = f"""请基于以下检索到的真实论文片段回答问题。

【重要引用规则】
- 必须在句末标注对应片段的序号，格式为 [1]、[2]。
- 严禁照抄检索片段中原本自带的参考文献编号（如 [40], [41] 等），那些编号与本系统无关。
- 如果检索片段无法支撑答案，请明确说明"当前挂载的文献中未找到相关信息"。
- 引用示例："...该方法在小目标检测上提升了12%的mAP[1]。"

问题：{question}

检索片段：
{context}"""

        system_prompt = """你是严谨的科研文献问答Agent。你必须：
1. 所有结论严格基于检索片段，不得编造。
2. 引用时使用 [1]、[2] 格式（对应片段序号），句末标注。
3. 绝对禁止在回答中出现检索片段里的原始参考文献编号（如 [40]、[41]）。"""
        answer_parts: list[str] = []
        async for piece in self.llm.stream_chat([{'role':'system','content': system_prompt}, {'role':'user','content':prompt}], temperature=0.1):
            answer_parts.append(piece)
            yield {'type': 'delta', 'content': piece}
        answer = ''.join(answer_parts)
        assistant_msg = QAMessage(session_id=session.id, role='assistant', content=answer); db.add(assistant_msg); await db.flush()
        await self._add_message_sources(db, assistant_msg.id, ranked)
        await db.commit()
        yield {'type': 'done', 'session_id': session.id, 'answer': answer}

    async def suggest_questions(self, db: AsyncSession, session_id: int) -> dict:
        """根据会话挂载的文献，用 LLM 生成 3-4 个推荐问题"""
        pids = (await db.execute(
            select(QASessionPaper.paper_id).where(QASessionPaper.session_id == session_id)
        )).scalars().all()
        if not pids:
            return {'questions': ['请先上传文献，我将为您生成推荐问题']}

        from app.models import PaperExtractedInfo
        infos = (await db.execute(
            select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id.in_(pids))
        )).scalars().all()

        titles = []
        snippets: list[str] = []
        for info in infos:
            titles.append(info.title or f'Paper {info.paper_id}')
            parts = []
            for field in ['abstract', 'research_question', 'method', 'main_results']:
                val = getattr(info, field, None)
                if val:
                    parts.append(f'{field}: {str(val)[:300]}')
            snippets.append(' '.join(parts))

        joined = '\n'.join([f'— {t}: {s}' for t, s in zip(titles, snippets)])[:3000]
        prompt = f"""根据以下文献信息，生成 4 个有深度的研究问题，供研究者深入探索。问题应该具有引导性，驱动用户对比、反思或验证。仅输出 JSON 数组字符串，格式：["问题1","问题2","问题3","问题4"]\n\n文献摘要：\n{joined}"""
        try:
            text = await self.llm.chat(
                [{'role': 'system', 'content': '你为研究者生成引导性问题。只输出 JSON 字符串数组。'},
                 {'role': 'user', 'content': prompt}],
                temperature=0.5, max_tokens=500,
            )
            import re
            m = re.search(r'\[.*\]', text, re.S)
            if m:
                from app.utils.json_utils import loads
                questions = loads(m.group(0), default=None)
                if isinstance(questions, list) and len(questions) > 0:
                    return {'questions': questions, 'session_id': session_id}
        except Exception:
            pass
        return {'questions': ['这些文献的核心创新点是什么？', '它们的方法论有何异同？', '实验结果的可复现性如何？', '该领域未来研究的方向是什么？'], 'session_id': session_id}

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
