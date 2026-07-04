from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agents.state import AgentState, ChatTurn
from app.prompts.qa import EMPTY_CONTEXT


async def prepare_context_node(state: AgentState, config: RunnableConfig) -> dict:
    """无 Milvus 检索时的上下文准备（通用问答 / 对话总结）。"""
    intent = state.get('intent') or 'general'
    history: list[ChatTurn] = state.get('chat_history') or []

    if intent == 'summarize_history' and history:
        lines = ['【对话历史摘要参考】']
        for turn in history[-12:]:
            role = '用户' if turn.get('role') == 'user' else '助手'
            content = (turn.get('content') or '')[:1500]
            if content.strip():
                lines.append(f'{role}：{content}')
        context_text = '\n\n'.join(lines)
    else:
        context_text = EMPTY_CONTEXT

    return {
        'context_text': context_text,
        'citable_ranked': [],
        'ranked_chunks': [],
    }
