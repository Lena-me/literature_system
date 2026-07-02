from __future__ import annotations

from collections import Counter, defaultdict
import re

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


DIMENSION_EVIDENCE_META = {
    'research_question': {
        'label': '研究问题',
        'query': '这篇论文要解决的核心研究问题、研究目标或任务定义是什么？',
        'fields': ['research_question', 'abstract'],
    },
    'method': {
        'label': '方法 / 模型',
        'query': '这篇论文提出或使用了什么方法、模型、系统框架或算法流程？',
        'fields': ['method'],
    },
    'experiment_data': {
        'label': '数据集 / 实验对象',
        'query': '这篇论文使用了什么数据集、基准、实验对象、任务设置或实验场景？',
        'fields': ['experiment_data'],
    },
    'metrics': {
        'label': '评价指标',
        'query': '这篇论文使用了哪些评价指标、评分规则、实验指标或评估口径？',
        'fields': ['experiment_data', 'main_results'],
    },
    'main_results': {
        'label': '主要结果',
        'query': '这篇论文的核心实验结果、主要发现和结论是什么？',
        'fields': ['main_results'],
    },
    'innovations': {
        'label': '创新点',
        'query': '这篇论文相对已有工作的主要贡献、创新点或改进是什么？',
        'fields': ['innovations'],
    },
    'limitations': {
        'label': '局限性',
        'query': '这篇论文提到了哪些不足、限制、风险、失败案例或适用边界？',
        'fields': ['limitations'],
    },
    'future_work': {
        'label': '未来方向',
        'query': '这篇论文提出了哪些未来工作、可扩展方向或后续研究问题？',
        'fields': ['future_work'],
    },
}

GLOBAL_BAD_SECTION_KEYWORDS = {
    'references',
    'bibliography',
    'table of contents',
    'contents',
    'appendix',
    'acknowledgement',
    'acknowledgements',
    'related work',
    'judge prompt',
    'judge prompts',
    'prompt templates',
    'system prompts',
    '参考文献',
    '目录',
    '附录',
    '致谢',
}

DIMENSION_BAD_SECTION_KEYWORDS = {
    'research_question': {'threats to validity', 'error taxonomy', 'case studies'},
    'method': {'threats to validity', 'judge prompt', 'system prompts', 'related work'},
    'experiment_data': {'threats to validity', 'judge prompt', 'system prompts', 'related work'},
    'metrics': {'threats to validity', 'system prompts', 'related work'},
    'main_results': {'threats to validity', 'judge prompt', 'system prompts', 'related work'},
    'innovations': {'threats to validity', 'judge prompt', 'system prompts', 'related work'},
}


def _is_generic_compare_question(question: str | None) -> bool:
    if not question:
        return True

    q = question.strip().lower()
    generic_tokens = [
        '比较这些论文',
        '对比这些论文',
        '比较这些文献',
        '对比这些文献',
        '这些论文',
        '这些文献',
        '多文献',
        '横向对比',
        'compare these papers',
        'compare papers',
    ]
    return any(token in q for token in generic_tokens)


def _is_low_quality_evidence(
    text: str,
    section_title: str | None = None,
    dimension_key: str | None = None,
) -> bool:
    content = (text or '').strip()
    lower = content.lower()
    section = (section_title or '').strip().lower()

    if len(content) < 80:
        return True
    if any(x in section for x in GLOBAL_BAD_SECTION_KEYWORDS):
        return True

    if any(x in lower[:300] for x in ['references', 'bibliography', 'table of contents']):
        return True

    if dimension_key:
        bad_for_dim = DIMENSION_BAD_SECTION_KEYWORDS.get(dimension_key, set())
        if any(x in section for x in bad_for_dim):
            return True

    bad_text_markers = [
        'verdict:[pass/fail]',
        'response format:',
        'decision logic:',
        'judge prompt',
        'system prompts',
        'threats in benchmark contamination',
        'the prompt is intentionally',
    ]
    if any(marker in lower for marker in bad_text_markers):
        return True

    citation_count = len(re.findall(r'\[\d+\]', content))
    arxiv_count = lower.count('arxiv preprint')
    proceedings_count = lower.count('proceedings of')
    if citation_count >= 4 or arxiv_count >= 2 or proceedings_count >= 2:
        return True

    numbered_toc = len(re.findall(r'\b\d+(?:\.\d+)*\s+[A-Z][A-Za-z ]{3,}', content[:1000]))
    if numbered_toc >= 6:
        return True

    symbol_count = sum(content.count(x) for x in ['$', '<sub>', '<sup>', '\\mathrm', '\\gets'])
    if symbol_count >= 6 and len(content) < 1200:
        return True

    return False


def _normalize_snippet(text: str, limit: int = 900) -> str:
    text = str(text or '')
    text = re.sub(r'</?(sub|sup)>', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('\\mathrm', '')
    text = text.replace('\\gets', '->')
    text = text.strip()

    match = re.search(r'([A-Z][A-Za-z][^。?!?]{40,}[。?!?])', text)
    if match and match.start() < 300:
        text = text[match.start():]

    return text[:limit]


def _looks_like_natural_evidence(text: str) -> bool:
    content = text or ''
    if len(content) < 80:
        return False

    alpha_count = sum(ch.isalpha() for ch in content)
    symbol_count = sum(content.count(x) for x in ['$', '<sub>', '<sup>', '\\', '{', '}'])

    if alpha_count < 50:
        return False
    if symbol_count > 12:
        return False

    return True


def _matches_dimension(text: str, section_title: str | None, dimension_key: str) -> bool:
    content = (text or '').lower()
    section = (section_title or '').lower()

    positive_keywords = {
        'research_question': [
            'we aim', 'we seek', 'this paper aims', 'we investigate',
            'we study', 'challenge', 'problem', 'goal', 'objective',
            'research question', 'task definition',
        ],
        'method': [
            'we propose', 'we introduce', 'framework', 'method',
            'approach', 'pipeline', 'architecture', 'algorithm',
            'system', 'model', 'harness', 'protocol',
        ],
        'experiment_data': [
            'dataset', 'benchmark', 'data collection', 'tasks',
            'experimental setup', 'task setup', 'evaluation setup',
            'instances', 'samples', 'cases',
        ],
        'metrics': [
            'metric', 'score', 'accuracy', 'precision', 'recall',
            'f1', 'auc', 'pass rate', 'evaluation', 'measure',
        ],
        'main_results': [
            'results', 'performance', 'outperform', 'achieves',
            'improves', 'we find', 'table', 'overall performance',
            'main results',
        ],
        'innovations': [
            'contribution', 'novel', 'first', 'new', 'we introduce',
            'we propose', 'innovation', 'unified', 'process-verified',
        ],
        'limitations': [
            'limitation', 'threat', 'fail', 'failure', 'risk',
            'weakness', 'future work', 'cannot', 'not address',
        ],
        'future_work': [
            'future work', 'future direction', 'further research',
            'we plan', 'could be extended', 'next step',
        ],
    }

    section_prefer = {
        'research_question': ['abstract', 'introduction'],
        'method': ['method', 'approach', 'framework', 'system', 'design'],
        'experiment_data': ['dataset', 'benchmark', 'data collection', 'experimental setup', 'task setup'],
        'metrics': ['metric', 'evaluation', 'experimental setup', 'results'],
        'main_results': ['result', 'experiment', 'evaluation', 'overall performance'],
        'innovations': ['abstract', 'introduction', 'conclusion'],
        'limitations': ['limitation', 'threat', 'discussion', 'conclusion'],
        'future_work': ['future', 'conclusion', 'discussion'],
    }

    positives = positive_keywords.get(dimension_key, [])
    prefers = section_prefer.get(dimension_key, [])
    return any(k in content for k in positives) or any(k in section for k in prefers)


def _structured_anchor(info: PaperExtractedInfo | None, fields: list[str], limit: int = 500) -> str:
    if not info:
        return ''

    parts = []
    for field in fields:
        value = getattr(info, field, None)
        if value and str(value).strip():
            parts.append(str(value).strip())

    return '\n'.join(parts)[:limit]


def _support_from_score(score: float | None) -> str:
    if score is None:
        return 'structured'
    return 'strong' if score >= 0.65 else 'related' if score >= 0.45 else 'weak'


def _make_evidence(
    paper: Paper,
    snippet: str,
    page_number: int | None,
    section_title: str | None,
    score: float | None,
    dimension_key: str,
) -> dict:
    text = _normalize_snippet(snippet)
    return {
        'paper_id': paper.id,
        'paper_title': paper.title or paper.original_filename,
        'snippet': text,
        'page_number': page_number or None,
        'section_title': section_title or '',
        'score': round(score, 4) if score is not None else None,
        'support': _support_from_score(score),
        'dimension_key': dimension_key,
        'source': {
            'paper_id': paper.id,
            'page_number': page_number or None,
            'section_title': section_title or '',
            'snippet': text,
        },
    }


@router.post('/evidence-matrix')
async def evidence_matrix(
    data: EvidenceMatrixIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    papers_raw = (
        await db.execute(
            select(Paper).where(
                Paper.id.in_(data.paper_ids),
                Paper.user_id == user.id,
                Paper.is_deleted == False,
            )
        )
    ).scalars().all()

    paper_map = {p.id: p for p in papers_raw}
    papers = [paper_map[pid] for pid in data.paper_ids if pid in paper_map]
    columns = ['Dimension', 'Paper', 'Evidence snippet', 'Page', 'Section', 'Support', 'Similarity']
    if not papers:
        return {'question': data.question, 'columns': columns, 'rows': [], 'dimensions': []}

    paper_ids = [p.id for p in papers]
    selected_dimension_keys = [x for x in (data.dimensions or []) if x in DIMENSION_EVIDENCE_META]
    if not selected_dimension_keys:
        selected_dimension_keys = [
            'research_question',
            'method',
            'experiment_data',
            'main_results',
            'innovations',
        ]

    infos = (
        await db.execute(
            select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id.in_(paper_ids))
        )
    ).scalars().all()
    info_map = {x.paper_id: x for x in infos}

    content_items = (
        await db.execute(
            select(ContentItem)
            .where(ContentItem.paper_id.in_(paper_ids))
            .order_by(ContentItem.paper_id.asc(), ContentItem.order_index.asc())
        )
    ).scalars().all()
    content_by_paper: dict[int, list[ContentItem]] = defaultdict(list)
    for item in content_items:
        content_by_paper[item.paper_id].append(item)

    try:
        embedding = BGEEmbedding()
        store = MilvusChunkStore()
    except Exception:
        embedding = None
        store = None

    dimension_blocks = []
    legacy_by_paper: dict[int, list[dict]] = defaultdict(list)

    for dim_key in selected_dimension_keys:
        meta = DIMENSION_EVIDENCE_META[dim_key]
        dim_query = meta['query']
        if data.question and not _is_generic_compare_question(data.question):
            dim_query = f"{meta['query']}\n用户补充关注：{data.question}"

        dim_rows = []

        for paper in papers:
            evidences: list[dict] = []
            seen = set()
            info = info_map.get(paper.id)
            anchor = _structured_anchor(info, meta['fields'])
            paper_query = dim_query
            if anchor:
                paper_query = f'{dim_query}\n该论文该维度的结构化摘要：{anchor}'

            if embedding is not None and store is not None:
                try:
                    query_vector = embedding.encode_query(paper_query)
                    candidates = store.search(query_vector, [paper.id], limit=16)
                except Exception:
                    candidates = []

                for c in candidates:
                    snippet = c.get('text') or ''
                    section_title = c.get('section_title') or ''
                    score = float(c.get('score') or 0)

                    if _is_low_quality_evidence(snippet, section_title, dim_key):
                        continue
                    if not _looks_like_natural_evidence(snippet):
                        continue
                    if not _matches_dimension(snippet, section_title, dim_key):
                        continue

                    normalized_key = _normalize_snippet(snippet, 160).lower()
                    if normalized_key in seen:
                        continue
                    seen.add(normalized_key)

                    evidences.append(
                        _make_evidence(
                            paper=paper,
                            snippet=snippet,
                            page_number=c.get('page_number') or None,
                            section_title=section_title,
                            score=score,
                            dimension_key=dim_key,
                        )
                    )
                    if evidences[-1].get('support') == 'weak':
                        evidences.pop()
                        continue
                    if len(evidences) >= 2:
                        break

            if not evidences and anchor:
                evidences.append(
                    _make_evidence(
                        paper=paper,
                        snippet=anchor,
                        page_number=None,
                        section_title='结构化抽取结果',
                        score=None,
                        dimension_key=dim_key,
                    )
                )

            if not evidences:
                for item in content_by_paper.get(paper.id, []):
                    text = (item.content or '').strip()
                    if _is_low_quality_evidence(text, item.item_type or '', dim_key):
                        continue
                    if not _looks_like_natural_evidence(text):
                        continue
                    if not _matches_dimension(text, item.item_type or '', dim_key):
                        continue
                    evidences.append(
                        _make_evidence(
                            paper=paper,
                            snippet=text,
                            page_number=item.page_number,
                            section_title=item.item_type or '',
                            score=None,
                            dimension_key=dim_key,
                        )
                    )
                    break

            for ev in evidences:
                legacy_by_paper[paper.id].append(ev)

            dim_rows.append(
                {
                    'paper_id': paper.id,
                    'title': paper.title or paper.original_filename,
                    'evidences': evidences,
                    'evidence_count': len(evidences),
                }
            )

        dimension_blocks.append(
            {
                'dimension_key': dim_key,
                'label': meta['label'],
                'query': dim_query,
                'rows': dim_rows,
            }
        )

    rows = []
    for paper in papers:
        evidences = legacy_by_paper.get(paper.id, [])[:5]
        rows.append(
            {
                'paper_id': paper.id,
                'title': paper.title or paper.original_filename,
                'evidences': evidences,
                'evidence_count': len(evidences),
            }
        )

    return {'question': data.question, 'columns': columns, 'rows': rows, 'dimensions': dimension_blocks}


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
