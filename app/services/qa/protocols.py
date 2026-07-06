from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class QARetrievalPort(Protocol):
    """文献检索与上下文构建（Agent 层唯一检索入口）。"""

    async def retrieve_stream(
        self,
        db: AsyncSession,
        query: str,
        paper_ids: list[int] | None,
        top_k: int | None,
    ) -> AsyncIterator[str | list[dict[str, Any]]]:
        """yield 阶段名 (str)，最后 yield ranked chunks (list)。"""
        ...

    def build_context(self, ranked: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        ...

    def extract_cited_sources(
        self, answer: str, citable_ranked: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ...


class QAMessagePort(Protocol):
    """问答消息持久化与修剪。"""

    async def delete_messages_after(
        self, db: AsyncSession, session_id: int, after_created_at: Any,
    ) -> None:
        ...

    async def attach_sources(
        self, db: AsyncSession, message_id: int, sources: list[dict[str, Any]],
    ) -> None:
        ...
