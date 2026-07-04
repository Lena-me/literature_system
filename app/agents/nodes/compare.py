from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.types import StreamWriter

from app.agents.state import AgentState
from app.agents.tools.compare import run_compare_papers


def _cfg(config: RunnableConfig) -> dict:
    return config.get('configurable') or {}


async def compare_papers_node(
    state: AgentState,
    config: RunnableConfig,
    writer: StreamWriter,
) -> dict:
    """执行多篇文献对比工具，将结果写入 context 供 generate 使用。"""
    cfg = _cfg(config)
    db = cfg['db']
    user_id: int = cfg['user_id']
    paper_ids = list(state.get('paper_ids') or [])

    writer({'type': 'status', 'stage': 'comparing'})

    try:
        tool_out = await run_compare_papers(db, user_id, paper_ids)
    except ValueError as exc:
        from app.prompts.qa import EMPTY_CONTEXT

        msg = str(exc)
        return {
            'error': msg,
            'context_text': f'{EMPTY_CONTEXT}\n\n（对比工具未能执行：{msg}）',
            'citable_ranked': [],
            'ranked_chunks': [],
            'tool_results': {'compare': {'error': msg}},
        }

    context_text = tool_out.get('context_text') or ''
    tool_results = dict(state.get('tool_results') or {})
    tool_results['compare'] = tool_out

    return {
        'context_text': context_text,
        'citable_ranked': [],
        'ranked_chunks': [],
        'tool_results': tool_results,
    }
