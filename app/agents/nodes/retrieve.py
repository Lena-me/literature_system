from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.types import StreamWriter

from app.agents.state import AgentState


def _cfg(config: RunnableConfig) -> dict:
    return config.get('configurable') or {}


async def retrieve_node(state: AgentState, config: RunnableConfig, writer: StreamWriter) -> dict:
    """检索文献片段，通过 StreamWriter 推送阶段状态。"""
    from app.services.rag_service import get_rag_service

    cfg = _cfg(config)
    db = cfg['db']
    rag = get_rag_service()

    query = state.get('retrieval_query') or state.get('question') or ''
    paper_ids = state.get('paper_ids')
    top_k = state.get('top_k')

    ranked: list[dict] | None = None
    async for item in rag._retrieve_ranked_stream(db, query, paper_ids, top_k):
        if isinstance(item, str):
            writer({'type': 'status', 'stage': item})
        else:
            ranked = item

    context_text, citable_ranked = rag._build_context(ranked or [])
    return {
        'ranked_chunks': ranked or [],
        'context_text': context_text,
        'citable_ranked': citable_ranked,
    }
