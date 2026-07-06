from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.services.qa import QAMessagePort, QARetrievalPort, build_qa_ports


@dataclass
class AgentDeps:
    """LangGraph 节点运行时依赖（与 AgentState 分离，便于测试与替换实现）。"""

    user_id: int
    llm: OpenAICompatibleLLM
    retrieval: QARetrievalPort
    messages: QAMessagePort
    cancel_ctrl: dict[str, bool]

    @asynccontextmanager
    async def db_session(self):
        """按需短连接：避免 SSE 长请求占满连接池。"""
        from app.db.mysql import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            yield session


def build_agent_deps(
    user_id: int,
    llm: OpenAICompatibleLLM,
    cancel_ctrl: dict[str, bool],
    *,
    retrieval: QARetrievalPort | None = None,
    messages: QAMessagePort | None = None,
) -> AgentDeps:
    if retrieval is None or messages is None:
        ret_adapter, msg_adapter = build_qa_ports()
        retrieval = retrieval or ret_adapter
        messages = messages or msg_adapter
    return AgentDeps(
        user_id=user_id,
        llm=llm,
        retrieval=retrieval,
        messages=messages,
        cancel_ctrl=cancel_ctrl,
    )


def get_deps(config: RunnableConfig) -> AgentDeps:
    cfg = config.get('configurable') or {}
    deps = cfg.get('deps')
    if deps is None:
        raise RuntimeError('AgentDeps 未注入，请通过 orchestrator 启动图')
    return deps


def is_cancelled(deps: AgentDeps, state: dict[str, Any] | None = None) -> bool:
    if deps.cancel_ctrl.get('cancelled'):
        return True
    return bool(state and state.get('cancelled'))
