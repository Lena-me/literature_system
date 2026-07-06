from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rag_service import RAGService


class RAGRetrievalAdapter:
    """RAGService → QARetrievalPort 适配器。"""

    def __init__(self, rag: RAGService) -> None:
        self._rag = rag

    async def retrieve_stream(
        self,
        db: AsyncSession,
        query: str,
        paper_ids: list[int] | None,
        top_k: int | None,
    ) -> AsyncIterator[str | list[dict[str, Any]]]:
        async for item in self._rag.retrieve_ranked_stream(db, query, paper_ids, top_k):
            yield item

    def build_context(self, ranked: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        return self._rag.build_retrieval_context(ranked)

    def extract_cited_sources(
        self, answer: str, citable_ranked: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return self._rag.extract_cited_sources(answer, citable_ranked)


class RAGMessageAdapter:
    """RAGService → QAMessagePort 适配器。"""

    def __init__(self, rag: RAGService) -> None:
        self._rag = rag

    async def delete_messages_after(
        self, db: AsyncSession, session_id: int, after_created_at: Any,
    ) -> None:
        await self._rag.delete_messages_after(db, session_id, after_created_at)

    async def attach_sources(
        self, db: AsyncSession, message_id: int, sources: list[dict[str, Any]],
    ) -> None:
        await self._rag.attach_message_sources(db, message_id, sources)
