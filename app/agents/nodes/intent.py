from __future__ import annotations

import re

from langchain_core.runnables import RunnableConfig
from langgraph.types import StreamWriter

from app.agents.state import AgentIntent, AgentState

_COMPARE_PATTERN = re.compile(
    r'对比|比较|异同|差异|区别|compare|comparison|versus|\bvs\.?\b',
    re.IGNORECASE,
)
_SUMMARIZE_PATTERN = re.compile(
    r'总结|汇总|概括|梳理|回顾|归纳|summarize|summary|recap',
    re.IGNORECASE,
)


def classify_intent(question: str, paper_ids: list[int] | None) -> AgentIntent:
    """规则优先的轻量意图分类（Phase 2；后续可换 LLM）。"""
    q = (question or '').strip()
    pids = paper_ids or []

    if _COMPARE_PATTERN.search(q) and len(pids) >= 2:
        return 'compare'

    if _SUMMARIZE_PATTERN.search(q) and ('对话' in q or '聊天' in q or '上文' in q or '刚才' in q):
        return 'summarize_history'

    if not pids:
        return 'general'

    return 'literature_qa'


async def classify_intent_node(
    state: AgentState,
    config: RunnableConfig,
    writer: StreamWriter,
) -> dict:
    writer({'type': 'status', 'stage': 'classifying'})

    question = state.get('question') or ''
    paper_ids = state.get('paper_ids') or []
    intent = classify_intent(question, paper_ids)

    return {'intent': intent, 'tool_results': state.get('tool_results') or {}}
