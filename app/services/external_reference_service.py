from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper, PaperExtractedInfo, QASessionPaper
from app.services.generation_service import GenerationService
from app.utils.paper_links import (
    clean_title_from_reference,
    dedupe_external_refs,
    extract_doi_from_text,
    extract_official_url_from_text,
    extract_answer_paper_titles,
    extract_recommended_papers_from_answer,
    extract_refs_from_answer_text,
    normalize_external_ref_item,
    resolve_official_paper_url,
    title_referenced_in_answer,
)

logger = logging.getLogger(__name__)

_USER_WANTS_REFS_RE = re.compile(
    r'推荐|列举|介绍.{0,8}论文|哪些论文|有什么论文|延伸阅读|拓展阅读|相关论文|文献推荐|'
    r'给我.{0,6}篇|找.{0,4}论文|论文推荐|阅读建议|阅读顺序',
    re.I,
)


def _normalize_title(title: str) -> str:
    return re.sub(r'\s+', ' ', (title or '').lower().strip())


def user_wants_external_refs(user_question: str | None) -> bool:
    """仅当用户明确在问推荐/拓展文献时为 True。"""
    return bool(_USER_WANTS_REFS_RE.search(user_question or ''))


async def _session_paper_ids(db: AsyncSession, session_id: int) -> list[int]:
    rows = (
        await db.execute(
            select(QASessionPaper.paper_id).where(QASessionPaper.session_id == session_id)
        )
    ).scalars().all()
    return [int(x) for x in rows]


async def _load_paper_source(db: AsyncSession, paper_id: int) -> dict:
    paper = await db.get(Paper, paper_id)
    info = (
        await db.execute(
            select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id == paper_id)
        )
    ).scalar_one_or_none()
    if not paper and not info:
        return {}
    return {
        'title': (info.title if info else None) or (paper.title if paper else None) or '',
        'keywords': (info.keywords if info else None) or (paper.keywords if paper else None) or '',
        'research_question': info.research_question if info else None,
        'method': info.method if info else None,
        'abstract': info.abstract if info else None,
        'doi': paper.doi if paper else None,
    }


async def _scan_library_refs(
    db: AsyncSession,
    *,
    answer: str,
    answer_titles: list[str],
    paper_ids: list[int],
    user_id: int | None,
    limit: int,
    append_ref,
) -> None:
    """扫描挂载文献参考文献与库内推荐（较重，仅用户索要文献时调用）。"""

    gen = GenerationService()
    for pid in paper_ids:
        try:
            source = await _load_paper_source(db, pid)
            if not source:
                continue

            trace_items = await gen._select_reference_trace_items(db, pid, source, limit=8)
            for row in trace_items:
                content = row.get('content') or ''
                doi = extract_doi_from_text(content)
                official_url = extract_official_url_from_text(content) or resolve_official_paper_url(doi)
                if not official_url:
                    continue
                clean = clean_title_from_reference(content)
                if not title_referenced_in_answer(clean, answer, answer_titles):
                    continue
                append_ref({
                    'title': clean,
                    'snippet': content[:500],
                    'doi': doi,
                    'official_url': official_url,
                    'source_type': 'reference_bibliography',
                    'paper_id': None,
                    'from_paper_id': pid,
                })

            if user_id:
                related = await gen._find_same_direction_different_method_papers(
                    db, user_id, pid, source, limit=3,
                )
                for row in related:
                    title = row.get('title') or ''
                    if not title_referenced_in_answer(title, answer, answer_titles):
                        continue
                    rid = row.get('paper_id')
                    paper = await db.get(Paper, rid) if rid else None
                    doi = paper.doi if paper else None
                    official_url = resolve_official_paper_url(doi)
                    if not official_url:
                        continue
                    append_ref({
                        'title': title,
                        'snippet': row.get('reason') or '',
                        'doi': doi,
                        'official_url': official_url,
                        'source_type': 'library_recommendation',
                        'paper_id': rid,
                        'from_paper_id': pid,
                    })
        except Exception as exc:
            logger.warning(
                'build_external_refs paper scan failed paper_id=%s: %s',
                pid,
                exc,
                exc_info=True,
            )


async def build_external_refs(
    db: AsyncSession,
    answer: str,
    *,
    paper_ids: list[int] | None = None,
    session_id: int | None = None,
    user_id: int | None = None,
    user_question: str | None = None,
    limit: int = 12,
    heavy_timeout: float = 8.0,
) -> list[dict]:
    """汇总回答中的外部/拓展文献（非 [n] 文库片段引用）。

    - 回答正文中的 DOI/arXiv/URL：始终提取
    - 推荐列表：按行解析完整论文标题，优先 DOI/arXiv 直链
    - 参考文献拓展 / 库内推荐：仅用户明确索要推荐文献时
    """
    if session_id and not paper_ids:
        paper_ids = await _session_paper_ids(db, session_id)

    refs: list[dict] = []
    seen_urls: set[str] = set()
    answer_titles: list[str] = []

    def append_ref(item: dict) -> bool:
        url = item.get('official_url')
        if not url or url in seen_urls:
            return False
        normalized = normalize_external_ref_item(item, answer, answer_titles or None)
        if not normalized:
            return False
        seen_urls.add(url)
        refs.append(normalized)
        return True

    wants_refs = user_wants_external_refs(user_question)
    if wants_refs:
        answer_titles = extract_answer_paper_titles(answer)
        for item in extract_recommended_papers_from_answer(answer, limit=limit * 2):
            append_ref(item)

    for item in extract_refs_from_answer_text(answer, limit=limit * 2):
        append_ref(item)

    if not wants_refs:
        return dedupe_external_refs(refs)[:limit]

    if len(refs) < limit:
        paper_ids = paper_ids or []
        if paper_ids:
            try:
                await asyncio.wait_for(
                    _scan_library_refs(
                        db,
                        answer=answer,
                        answer_titles=answer_titles,
                        paper_ids=paper_ids,
                        user_id=user_id,
                        limit=limit,
                        append_ref=append_ref,
                    ),
                    timeout=heavy_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning('build_external_refs library scan timed out after %.1fs', heavy_timeout)
            except Exception as exc:
                logger.warning('build_external_refs library scan failed: %s', exc, exc_info=True)

    return dedupe_external_refs(refs)[:limit]
