from __future__ import annotations

from typing import Any, Literal

from typing_extensions import TypedDict

StreamStage = Literal['embedding', 'searching', 'reranking', 'generating', 'classifying', 'comparing']

AgentIntent = Literal['literature_qa', 'compare', 'general', 'summarize_history']


class ChatTurn(TypedDict):
    role: str
    content: str


class AgentState(TypedDict, total=False):
    """LangGraph 共享状态（不含 DB Session 等运行时对象）。"""

    user_id: int
    session_id: int | None
    question: str
    paper_ids: list[int] | None
    top_k: int | None
    regenerate: bool

    chat_history: list[ChatTurn]
    retrieval_query: str
    intent: AgentIntent
    tool_results: dict[str, Any]

    ranked_chunks: list[dict[str, Any]]
    context_text: str
    citable_ranked: list[dict[str, Any]]

    answer: str
    reasoning: str
    cited_sources: list[dict[str, Any]]
    message_id: int | None

    error: str | None
