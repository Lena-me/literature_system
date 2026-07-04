from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import get_qa_graph
from app.agents.state import AgentState
from app.integrations.llm.openai_compatible import OpenAICompatibleLLM

logger = logging.getLogger(__name__)

_orchestrator: 'QAOrchestrator | None' = None


class QAOrchestrator:
    """LangGraph 编排入口：将图执行事件适配为现有 SSE 协议。"""

    def __init__(self) -> None:
        self.graph = get_qa_graph()
        self.llm = OpenAICompatibleLLM()

    async def ask_stream(
        self,
        db: AsyncSession,
        user_id: int,
        question: str,
        paper_ids: list[int] | None,
        session_id: int | None,
        top_k: int | None,
        *,
        regenerate: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        initial: AgentState = {
            'user_id': user_id,
            'session_id': session_id,
            'question': question,
            'paper_ids': paper_ids,
            'top_k': top_k,
            'regenerate': regenerate,
        }
        config: RunnableConfig = {
            'configurable': {
                'db': db,
                'user_id': user_id,
                'llm': self.llm,
            },
        }

        session_emitted = False

        try:
            async for mode, chunk in self.graph.astream(
                initial,
                config=config,
                stream_mode=['custom', 'updates'],
            ):
                if mode == 'custom':
                    event = chunk
                    if isinstance(event, dict):
                        if event.get('type') == 'session':
                            session_emitted = True
                        yield event
                    continue

                if mode != 'updates' or not isinstance(chunk, dict):
                    continue

                for node_name, update in chunk.items():
                    if node_name == 'prepare' and isinstance(update, dict):
                        sid = update.get('session_id')
                        if sid and not session_emitted:
                            session_emitted = True
                            yield {'type': 'session', 'session_id': sid}

        except Exception as exc:
            logger.error('QAOrchestrator.ask_stream failed: %s', exc, exc_info=True)
            yield {'type': 'error', 'error': str(exc)}


def get_qa_orchestrator() -> QAOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = QAOrchestrator()
    return _orchestrator
