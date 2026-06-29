from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.integrations.embeddings.bge_embedding import BGEEmbedding
from app.integrations.milvus.client import MilvusChunkStore
from app.models import ContentItem, LearningRecord, Paper, PaperExtractedInfo, QAMessage, User
from app.schemas import EvidenceMatrixIn, ResearchRadarIn

router = APIRouter(prefix='/analytics', tags=['research analytics'])


@router.post('/evidence-matrix')
async def evidence_matrix(
    data: EvidenceMatrixIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    papers = (
        await db.execute(
            select(Paper).where(
                Paper.id.in_(data.paper_ids),
                Paper.user_id == user.id,
                Paper.is_deleted == False,
            )
        )
    ).scalars().all()

    columns = ['Paper', 'Evidence snippet', 'Page', 'Section', 'Support', 'Similarity']
    if not papers:
        return {'question': data.question, 'columns': columns, 'rows': []}

    paper_ids = [p.id for p in papers]
    paper_map = {p.id: p for p in papers}
    evidence_by_paper: dict[int, list[dict]] = defaultdict(list)

    if data.question:
        try:
            query_vector = BGEEmbedding().encode_query(data.question)
            candidates = MilvusChunkStore().search(query_vector, paper_ids, limit=max(20, len(paper_ids) * 5))
        except Exception:
            candidates = []

        for c in candidates:
            pid = int(c.get('paper_id') or 0)
            if pid not in paper_map:
                continue

            score = float(c.get('score') or 0)
            support = 'strong' if score >= 0.65 else 'related' if score >= 0.45 else 'weak'
            snippet = c.get('text') or ''
            page_number = c.get('page_number') or None
            section_title = c.get('section_title') or ''
            evidence_by_paper[pid].append(
                {
                    'paper_id': pid,
                    'paper_title': paper_map[pid].title or paper_map[pid].original_filename,
                    'snippet': snippet,
                    'page_number': page_number,
                    'section_title': section_title,
                    'score': round(score, 4),
                    'support': support,
                    'source': {
                        'paper_id': pid,
                        'page_number': page_number,
                        'section_title': section_title,
                        'snippet': snippet,
                    },
                }
            )

    if not any(evidence_by_paper.values()):
        items = (
            await db.execute(
                select(ContentItem)
                .where(ContentItem.paper_id.in_(paper_ids))
                .order_by(ContentItem.paper_id.asc(), ContentItem.order_index.asc())
            )
        ).scalars().all()

        for item in items:
            if len(evidence_by_paper[item.paper_id]) >= 3:
                continue
            text = (item.content or '').strip()
            if not text:
                continue
            snippet = text[:800]
            evidence_by_paper[item.paper_id].append(
                {
                    'paper_id': item.paper_id,
                    'paper_title': paper_map[item.paper_id].title or paper_map[item.paper_id].original_filename,
                    'snippet': snippet,
                    'page_number': item.page_number,
                    'section_title': '',
                    'score': None,
                    'support': 'pending',
                    'source': {
                        'paper_id': item.paper_id,
                        'page_number': item.page_number,
                        'section_title': '',
                        'snippet': snippet,
                    },
                }
            )

    rows = []
    for p in papers:
        evidences = evidence_by_paper.get(p.id, [])[:5]
        rows.append(
            {
                'paper_id': p.id,
                'title': p.title or p.original_filename,
                'evidences': evidences,
                'evidence_count': len(evidences),
            }
        )

    return {'question': data.question, 'columns': columns, 'rows': rows}


@router.post('/research-radar')
async def research_radar(
    data: ResearchRadarIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    infos = (
        await db.execute(select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id.in_(data.paper_ids)))
    ).scalars().all()
    fields = [
        ('abstract', 'abstract'),
        ('research_question', 'question'),
        ('method', 'method'),
        ('experiment_data', 'experiment'),
        ('main_results', 'result'),
        ('innovations', 'innovation'),
        ('limitations', 'limitation'),
    ]
    radar = []
    for key, label in fields:
        filled = sum(1 for i in infos if getattr(i, key, None))
        radar.append({'dimension': label, 'score': round(filled / max(len(infos), 1) * 100, 2)})
    return {'radar': radar, 'paper_count': len(infos)}


@router.get('/hotspots')
async def hotspots(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    messages = (await db.execute(select(QAMessage.content).limit(300))).all()
    words = Counter()
    for (text,) in messages:
        normalized = str(text).replace(',', ' ').replace('.', ' ').replace('\n', ' ')
        for token in normalized.split():
            if len(token) >= 2:
                words[token[:12]] += 1
    return {'hotspots': [{'word': k, 'count': v} for k, v in words.most_common(30)]}
