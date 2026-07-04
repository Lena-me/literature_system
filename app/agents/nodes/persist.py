from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.types import StreamWriter

from app.agents.state import AgentState
from app.models import QAMessage
from app.services.source_enrichment import enrich_qa_sources


def _cfg(config: RunnableConfig) -> dict:
    return config.get('configurable') or {}


async def persist_node(state: AgentState, config: RunnableConfig, writer: StreamWriter) -> dict:
    """入库 assistant 消息与引用来源。"""
    from app.services.rag_service import get_rag_service

    cfg = _cfg(config)
    db = cfg['db']
    rag = get_rag_service()

    session_id = state.get('session_id')
    if not session_id:
        raise ValueError('缺少 session_id')

    answer = state.get('answer') or ''
    reasoning = state.get('reasoning') or ''
    cited_sources = list(state.get('cited_sources') or [])

    if cited_sources:
        cited_sources = await enrich_qa_sources(db, cited_sources, answer_text=answer)

    writer({'type': 'sources', 'sources': cited_sources})

    assistant_msg = QAMessage(
        session_id=session_id,
        role='assistant',
        content=answer,
        reasoning_content=reasoning or None,
    )
    db.add(assistant_msg)
    await db.flush()
    await rag._add_message_sources(db, assistant_msg.id, cited_sources)
    await db.commit()

    writer({
        'type': 'done',
        'session_id': session_id,
        'answer': answer,
        'reasoning': reasoning,
        'message_id': assistant_msg.id,
        'sources': cited_sources,
    })

    return {'message_id': assistant_msg.id, 'cited_sources': cited_sources}
