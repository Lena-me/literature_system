from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState, ChatTurn
from app.core.config import get_settings
from app.models import QAMessage, QASession, QASessionPaper


def _cfg(config: RunnableConfig) -> dict:
    return config.get('configurable') or {}


def build_retrieval_query(question: str, history: list[ChatTurn]) -> str:
    """结合最近对话，改写检索 query（轻量版，后续可换 LLM rewrite）。"""
    if not history:
        return question
    recent = history[-4:]
    lines = [f"{m['role']}: {(m['content'] or '')[:400]}" for m in recent]
    return '对话背景：\n' + '\n'.join(lines) + f'\n\n当前问题：{question}'


async def load_chat_history(
    db: AsyncSession,
    session_id: int,
    *,
    limit: int = 20,
    exclude_last_user: bool = False,
) -> list[ChatTurn]:
    rows = (
        await db.execute(
            select(QAMessage)
            .where(QAMessage.session_id == session_id)
            .order_by(QAMessage.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    rows = list(reversed(rows))
    history: list[ChatTurn] = []
    for msg in rows:
        if msg.role not in ('user', 'assistant'):
            continue
        history.append({'role': msg.role, 'content': msg.content or ''})
    if exclude_last_user and history and history[-1]['role'] == 'user':
        history = history[:-1]
    return history


async def prepare_session_node(state: AgentState, config: RunnableConfig) -> dict:
    """创建/校验会话、写入用户消息、加载对话历史。"""
    cfg = _cfg(config)
    db: AsyncSession = cfg['db']
    user_id: int = cfg['user_id']
    question = (state.get('question') or '').strip()
    paper_ids = state.get('paper_ids')
    session_id = state.get('session_id')
    regenerate = bool(state.get('regenerate'))

    settings = get_settings()
    history_limit = settings.qa_history_limit

    if regenerate:
        if not session_id:
            raise ValueError('重新生成需要指定 session_id')
        session = await db.get(QASession, session_id)
        if not session or session.user_id != user_id:
            raise ValueError('会话不存在或无权访问')
        last_user = (
            await db.execute(
                select(QAMessage)
                .where(QAMessage.session_id == session_id, QAMessage.role == 'user')
                .order_by(QAMessage.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not last_user:
            raise ValueError('没有可重新生成的用户问题')
        question = last_user.content
        from app.services.rag_service import get_rag_service

        rag = get_rag_service()
        await rag._delete_messages_after(db, session_id, last_user.created_at)
        await db.flush()
        history = await load_chat_history(db, session_id, limit=history_limit)
    else:
        session = await _get_or_create_session(db, user_id, paper_ids, session_id)
        user_msg = QAMessage(session_id=session.id, role='user', content=question)
        db.add(user_msg)
        await db.flush()
        history = await load_chat_history(db, session.id, limit=history_limit, exclude_last_user=True)

    resolved_paper_ids = await _resolve_paper_ids(db, session.id, paper_ids)
    retrieval_query = build_retrieval_query(question, history)
    return {
        'session_id': session.id,
        'question': question,
        'paper_ids': resolved_paper_ids,
        'chat_history': history,
        'retrieval_query': retrieval_query,
    }


async def _resolve_paper_ids(
    db: AsyncSession,
    session_id: int,
    paper_ids: list[int] | None,
) -> list[int]:
    """请求未带 paper_ids 时，从会话挂载文献读取。"""
    if paper_ids:
        seen: set[int] = set()
        ordered: list[int] = []
        for pid in paper_ids:
            if pid not in seen:
                seen.add(pid)
                ordered.append(pid)
        return ordered
    rows = (
        await db.execute(
            select(QASessionPaper.paper_id).where(QASessionPaper.session_id == session_id)
        )
    ).scalars().all()
    return list(rows)


async def _get_or_create_session(
    db: AsyncSession,
    user_id: int,
    paper_ids: list[int] | None,
    session_id: int | None,
) -> QASession:
    if session_id:
        session = await db.get(QASession, session_id)
        if session and session.user_id == user_id:
            return session
    session = QASession(user_id=user_id, title='新对话')
    db.add(session)
    await db.flush()
    for pid in paper_ids or []:
        db.add(QASessionPaper(session_id=session.id, paper_id=pid))
    await db.flush()
    return session
