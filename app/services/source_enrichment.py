from __future__ import annotations

import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ContentItem, FiguresTable, Paper, TextChunk
from app.utils.chunk_quality import normalize_page_number, normalize_chunk_text
from app.utils.paper_links import resolve_official_paper_url

_FIG_REF_RE = re.compile(
    r'(?:如图|图\s*(?![像示])|[Ff]ig(?:ure)?\.?\s*)([0-9]+(?:\.[0-9]+)*)',
    re.I,
)
_TABLE_REF_RE = re.compile(r'(?:如表|表\s*(?![格明])|[Tt]able\s*)([0-9]+(?:\.[0-9]+)*)')
_ABSTRACT_HEADING = re.compile(
    r'^(?:abstract|summary|摘要|内容摘要|英文摘要|中文摘要)\s*$',
    re.I,
)


def _normalize_bbox(raw) -> list[float] | None:
    if not raw:
        return None
    if isinstance(raw, dict):
        if all(k in raw for k in ('left', 'top', 'width', 'height')):
            left = float(raw['left'])
            top = float(raw['top'])
            width = float(raw['width'])
            height = float(raw['height'])
            return [left, top, left + width, top + height]
        return None
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            nums = [float(v) for v in raw]
        except (TypeError, ValueError):
            return None
        if all(v == v for v in nums):  # not NaN
            return nums
    return None


def _figure_dict(fig: FiguresTable, locator: dict | None = None) -> dict:
    out = {
        'id': fig.id,
        'type': fig.type,
        'caption': (fig.caption or '').strip() or None,
        'page_number': fig.page_number,
        'image_path': fig.image_path,
    }
    if locator:
        if locator.get('bbox'):
            out['bbox'] = locator['bbox']
        if locator.get('page_number') is not None:
            out['page_number'] = locator['page_number']
        if locator.get('locate_snippet'):
            out['locate_snippet'] = locator['locate_snippet']
        if locator.get('section_id'):
            out['section_id'] = locator['section_id']
    return out


def _caption_matches_figure(ref: str, caption: str) -> bool:
    cap = caption or ''
    patterns = (
        f'图 {ref}',
        f'图{ref}',
        f'Figure {ref}',
        f'Fig. {ref}',
        f'Fig {ref}',
    )
    if not any(p.lower() in cap.lower() for p in patterns):
        return False
    return not re.search(rf'表\s*{re.escape(ref)}', cap)


def _caption_matches_table(ref: str, caption: str) -> bool:
    cap = caption or ''
    patterns = (f'表 {ref}', f'表{ref}', f'Table {ref}')
    return any(p.lower() in cap.lower() for p in patterns)


def _match_visuals_by_text(
    text: str,
    visuals: list[FiguresTable],
    limit: int = 2,
    *,
    kind: str | None = None,
    locators: dict[int, dict] | None = None,
) -> list[dict]:
    if not text or not visuals:
        return []

    fig_refs = _FIG_REF_RE.findall(text)
    table_refs = _TABLE_REF_RE.findall(text)
    if not fig_refs and not table_refs:
        return []

    matched: list[dict] = []
    seen: set[int] = set()

    def try_add(visual: FiguresTable, ref: str, visual_kind: str) -> bool:
        if visual.id in seen:
            return False
        caption = visual.caption or ''
        if visual.type != visual_kind:
            return False
        if visual_kind == 'figure' and not _caption_matches_figure(ref, caption):
            return False
        if visual_kind == 'table' and not _caption_matches_table(ref, caption):
            return False
        locator = (locators or {}).get(int(visual.id))
        matched.append(_figure_dict(visual, locator))
        seen.add(visual.id)
        return True

    if kind in (None, 'figure'):
        for ref in fig_refs:
            for visual in visuals:
                if try_add(visual, ref, 'figure') and len(matched) >= limit:
                    return matched

    if kind in (None, 'table'):
        for ref in table_refs:
            for visual in visuals:
                if try_add(visual, ref, 'table') and len(matched) >= limit:
                    return matched

    return matched[:limit]


async def _load_visual_locators(db: AsyncSession, paper_ids: set[int]) -> dict[int, dict]:
    """FiguresTable.id → PDF 定位信息（bbox / 页码），与 ContentItem 按类型顺序对齐。"""
    if not paper_ids:
        return {}

    item_rows = (
        await db.execute(
            select(ContentItem)
            .where(
                ContentItem.paper_id.in_(paper_ids),
                ContentItem.item_type.in_(('figure', 'table')),
            )
            .order_by(ContentItem.paper_id.asc(), ContentItem.order_index.asc())
        )
    ).scalars().all()

    visual_rows = (
        await db.execute(
            select(FiguresTable)
            .where(FiguresTable.paper_id.in_(paper_ids))
            .order_by(FiguresTable.paper_id.asc(), FiguresTable.order_index.asc())
        )
    ).scalars().all()

    items_by_paper: dict[int, list[ContentItem]] = {}
    for item in item_rows:
        items_by_paper.setdefault(int(item.paper_id), []).append(item)

    visuals_by_paper: dict[int, list[FiguresTable]] = {}
    for visual in visual_rows:
        visuals_by_paper.setdefault(int(visual.paper_id), []).append(visual)

    locators: dict[int, dict] = {}
    for paper_id, visuals in visuals_by_paper.items():
        items = items_by_paper.get(paper_id, [])
        cursor = 0
        for visual in visuals:
            while cursor < len(items) and items[cursor].item_type != visual.type:
                cursor += 1
            if cursor >= len(items):
                break
            item = items[cursor]
            cursor += 1
            caption = (visual.caption or '').strip()
            locators[int(visual.id)] = {
                'bbox': _normalize_bbox(item.bbox),
                'page_number': normalize_page_number(item.page_number or visual.page_number),
                'section_id': int(item.id),
                'locate_snippet': caption[:200] if caption else None,
            }
    return locators


def _anchor_from_item(item: ContentItem, content: str, section_title: str) -> dict:
    return {
        'section_id': item.id,
        'page_number': normalize_page_number(item.page_number),
        'bbox': _normalize_bbox(item.bbox),
        'section_title': section_title,
        'locate_snippet': content[:300],
        'locate_type': 'abstract',
    }


def _pick_abstract_anchor(items: list[ContentItem]) -> dict | None:
    for item in items:
        if item.item_type == 'abstract':
            content = normalize_chunk_text(item.content or '')
            if len(content) >= 40:
                return _anchor_from_item(item, content, '摘要')

    in_abstract = False
    for item in items:
        content = normalize_chunk_text(item.content or '')
        if item.item_type == 'heading' and _ABSTRACT_HEADING.match(content.strip()):
            in_abstract = True
            continue
        if in_abstract:
            if item.item_type == 'heading':
                break
            if item.item_type in ('paragraph', 'list', 'abstract') and len(content) >= 40:
                return _anchor_from_item(item, content, '摘要')
    return None


async def _load_abstract_anchors(db: AsyncSession, paper_ids: set[int]) -> dict[int, dict]:
    if not paper_ids:
        return {}
    rows = (
        await db.execute(
            select(ContentItem)
            .where(ContentItem.paper_id.in_(paper_ids))
            .order_by(ContentItem.paper_id.asc(), ContentItem.order_index.asc())
        )
    ).scalars().all()
    by_paper: dict[int, list[ContentItem]] = {}
    for item in rows:
        by_paper.setdefault(int(item.paper_id), []).append(item)

    anchors: dict[int, dict] = {}
    for paper_id, items in by_paper.items():
        anchor = _pick_abstract_anchor(items)
        if anchor:
            anchors[paper_id] = anchor
    return anchors


async def _find_body_chunk_anchor(
    db: AsyncSession,
    paper_id: int,
    hint_text: str,
) -> dict | None:
    """摘要类来源兜底：在正文中按关键词查找可定位 chunk。"""
    if not hint_text or len(hint_text.strip()) < 8:
        return None

    keywords: list[str] = []
    for term in re.findall(r'[\u4e00-\u9fff]{2,8}', hint_text):
        if term not in {'这个', '那个', '什么', '如何', '为什么', '方法', '模型', '论文', '文献', '摘要', '结果'}:
            keywords.append(term)
    for term in re.findall(r'[A-Za-z][A-Za-z0-9_-]{2,}', hint_text):
        keywords.append(term)
    keywords = list(dict.fromkeys(keywords))[:6]
    if not keywords:
        return None

    clauses = [TextChunk.chunk_text.ilike(f'%{kw}%') for kw in keywords]
    rows = (
        await db.execute(
            select(TextChunk, ContentItem)
            .outerjoin(ContentItem, TextChunk.section_id == ContentItem.id)
            .where(TextChunk.paper_id == paper_id, or_(*clauses))
            .limit(12)
        )
    ).all()
    best: tuple[int, TextChunk, ContentItem | None] | None = None
    for chunk, item in rows:
        text = normalize_chunk_text(chunk.chunk_text or '')
        if len(text) < 40:
            continue
        score = sum(1 for kw in keywords if kw.lower() in text.lower())
        if best is None or score > best[0]:
            best = (score, chunk, item)
    if not best or best[0] <= 0:
        return None
    _, chunk, item = best
    content = normalize_chunk_text(chunk.chunk_text or '')
    section_title = chunk.section_title if hasattr(chunk, 'section_title') else None
    section_title = section_title or '正文'
    return {
        'chunk_id': int(chunk.id),
        'section_id': chunk.section_id,
        'page_number': normalize_page_number(chunk.page_number) or normalize_page_number(item.page_number if item else None),
        'bbox': _normalize_bbox(item.bbox if item else None),
        'section_title': section_title,
        'locate_snippet': content[:300],
        'locate_type': 'bbox' if item and item.bbox else 'page',
        'text': content,
        'snippet': content[:1000],
    }


def _apply_locate_meta(out: dict, anchor: dict | None) -> dict:
    if anchor:
        if anchor.get('chunk_id'):
            out['chunk_id'] = anchor['chunk_id']
        if not out.get('page_number') and anchor.get('page_number'):
            out['page_number'] = anchor['page_number']
        if not out.get('bbox') and anchor.get('bbox'):
            out['bbox'] = anchor['bbox']
        if not out.get('section_id') and anchor.get('section_id'):
            out['section_id'] = anchor['section_id']
        if anchor.get('section_title'):
            out['section_title'] = anchor['section_title']
        if anchor.get('locate_snippet'):
            out['locate_snippet'] = anchor['locate_snippet']
        if anchor.get('text'):
            out['text'] = anchor['text']
            out['snippet'] = anchor.get('snippet') or anchor['text'][:1000]
        if anchor.get('locate_type') == 'bbox' or anchor.get('bbox'):
            out['locate_type'] = 'bbox'
            out.pop('synthetic', None)
        elif out.get('synthetic') or out.get('section_title') == '摘要概要':
            out['section_title'] = anchor.get('section_title') or '摘要'
            out['locate_type'] = 'abstract'
    if out.get('bbox'):
        out['locate_type'] = out.get('locate_type') or 'bbox'
    elif out.get('page_number'):
        out['locate_type'] = out.get('locate_type') or 'page'
    else:
        out['locate_type'] = out.get('locate_type') or 'none'
    return out


async def enrich_qa_sources(
    db: AsyncSession,
    sources: list[dict],
    answer_text: str | None = None,
) -> list[dict]:
    """为问答引用补充正文、页码、bbox、字符偏移与相关图表。"""
    if not sources:
        return sources

    chunk_ids = {int(c['chunk_id']) for c in sources if c.get('chunk_id')}
    chunk_meta: dict[int, dict] = {}
    if chunk_ids:
        rows = await db.execute(
            select(TextChunk, ContentItem)
            .outerjoin(ContentItem, TextChunk.section_id == ContentItem.id)
            .where(TextChunk.id.in_(chunk_ids))
        )
        for chunk, item in rows.all():
            chunk_text = normalize_chunk_text(chunk.chunk_text or '')
            page_number = normalize_page_number(chunk.page_number) or normalize_page_number(
                item.page_number if item else None
            )
            chunk_meta[int(chunk.id)] = {
                'chunk_id': int(chunk.id),
                'section_id': chunk.section_id,
                'start_position': chunk.start_position,
                'end_position': chunk.end_position,
                'chunk_text': chunk_text,
                'page_number': page_number,
                'bbox': _normalize_bbox(item.bbox if item else None),
            }

    paper_ids = {int(c['paper_id']) for c in sources if c.get('paper_id')}
    papers_by_id: dict[int, Paper] = {}
    if paper_ids:
        paper_rows = (
            await db.execute(select(Paper).where(Paper.id.in_(paper_ids)))
        ).scalars().all()
        papers_by_id = {int(p.id): p for p in paper_rows}

    abstract_anchors = await _load_abstract_anchors(db, paper_ids)
    visual_locators = await _load_visual_locators(db, paper_ids)
    visuals_by_paper: dict[int, list[FiguresTable]] = {}
    if paper_ids:
        visual_rows = (
            await db.execute(
                select(FiguresTable)
                .where(FiguresTable.paper_id.in_(paper_ids))
                .order_by(FiguresTable.paper_id.asc(), FiguresTable.order_index.asc())
            )
        ).scalars().all()
        for visual in visual_rows:
            visuals_by_paper.setdefault(int(visual.paper_id), []).append(visual)

    # 从回答文本按论文聚合图表（避免每个 chunk 重复匹配、图/表混淆）
    answer_figures_by_paper: dict[int, list[dict]] = {}
    if answer_text:
        for pid in paper_ids:
            paper_visuals = visuals_by_paper.get(int(pid), [])
            if not paper_visuals:
                continue
            matched = _match_visuals_by_text(
                answer_text,
                paper_visuals,
                limit=6,
                locators=visual_locators,
            )
            if matched:
                answer_figures_by_paper[int(pid)] = matched

    enriched: list[dict] = []
    for src in sources:
        out = dict(src)
        cid = out.get('chunk_id')
        meta = chunk_meta.get(int(cid)) if cid is not None else None

        if meta:
            out.update(meta)
            clean_text = meta.get('chunk_text') or ''
            if clean_text:
                out['text'] = clean_text
                out['snippet'] = clean_text[:1000]
            db_page = meta.get('page_number')
            if db_page is not None:
                out['page_number'] = db_page
        else:
            raw_text = normalize_chunk_text(out.get('text') or out.get('snippet') or '')
            if raw_text:
                out['text'] = raw_text
                out['snippet'] = raw_text[:1000]

        out['page_number'] = normalize_page_number(out.get('page_number'))

        paper_id = out.get('paper_id')
        page_number = out.get('page_number')
        text = out.get('text') or out.get('snippet') or ''
        is_synthetic = bool(out.get('synthetic'))
        related: list[dict] = []
        seen_ids: set[int] = set()

        if paper_id is not None and not is_synthetic:
            paper_visuals = visuals_by_paper.get(int(paper_id), [])
            for item in _match_visuals_by_text(
                text, paper_visuals, limit=2, locators=visual_locators
            ):
                if item['id'] not in seen_ids:
                    related.append(item)
                    seen_ids.add(item['id'])
            for item in answer_figures_by_paper.get(int(paper_id), []):
                if item['id'] not in seen_ids:
                    related.append(item)
                    seen_ids.add(item['id'])

        out['related_figures'] = related[:6]

        if paper_id is not None:
            paper = papers_by_id.get(int(paper_id))
            if paper:
                out['paper_title'] = paper.title or paper.original_filename
                out['doi'] = paper.doi
                out['journal_conf'] = paper.journal_conf
                out['official_url'] = resolve_official_paper_url(paper.doi)

        anchor = abstract_anchors.get(int(paper_id)) if paper_id is not None else None
        needs_anchor = bool(
            out.get('synthetic')
            or (not out.get('bbox') and not out.get('page_number'))
        )
        if is_synthetic and paper_id is not None and answer_text:
            body_anchor = await _find_body_chunk_anchor(db, int(paper_id), answer_text)
            if body_anchor:
                anchor = body_anchor
                needs_anchor = True
        elif needs_anchor and anchor:
            pass
        if needs_anchor and anchor:
            out = _apply_locate_meta(out, anchor)
        else:
            out = _apply_locate_meta(out, None)

        enriched.append(out)
    return enriched
