from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.types import StreamWriter

from app.prompts.qa import COMPARE_ANSWER_HINT, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.agents.state import AgentState, ChatTurn
from app.integrations.llm.openai_compatible import OpenAICompatibleLLM


def _cfg(config: RunnableConfig) -> dict:
    return config.get('configurable') or {}


def _build_llm_messages(state: AgentState) -> list[dict]:
    question = state.get('question') or ''
    context = state.get('context_text') or ''
    history: list[ChatTurn] = state.get('chat_history') or []

    user_content = USER_PROMPT_TEMPLATE.format(question=question, context=context)
    if state.get('intent') == 'compare' or (state.get('tool_results') or {}).get('compare'):
        user_content = f'{user_content}\n\n{COMPARE_ANSWER_HINT}'

    messages: list[dict] = [{'role': 'system', 'content': SYSTEM_PROMPT}]

    for turn in history[-8:]:
        content = (turn.get('content') or '')[:2500]
        if not content.strip():
            continue
        messages.append({'role': turn['role'], 'content': content})

    messages.append({'role': 'user', 'content': user_content})
    return messages


async def generate_node(state: AgentState, config: RunnableConfig, writer: StreamWriter) -> dict:
    """流式生成回答，delta 经 StreamWriter 推送。"""
    cfg = _cfg(config)
    llm: OpenAICompatibleLLM = cfg.get('llm') or OpenAICompatibleLLM()
    from app.services.rag_service import get_rag_service

    rag = get_rag_service()

    writer({'type': 'status', 'stage': 'generating'})

    messages = _build_llm_messages(state)
    reasoning_parts: list[str] = []
    answer_parts: list[str] = []

    async for channel, piece in llm.stream_chat(messages, temperature=0.35):
        if channel == 'reasoning':
            reasoning_parts.append(piece)
            writer({'type': 'delta', 'channel': 'reasoning', 'content': piece})
        else:
            answer_parts.append(piece)
            writer({'type': 'delta', 'channel': 'content', 'content': piece})

    answer = ''.join(answer_parts)
    reasoning = ''.join(reasoning_parts)
    citable = state.get('citable_ranked') or []
    cited_sources = rag._sources_cited_in_answer(answer, citable)

    return {
        'answer': answer,
        'reasoning': reasoning,
        'cited_sources': cited_sources,
    }
