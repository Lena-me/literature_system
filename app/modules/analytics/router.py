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
from app.models import ContentItem, LearningRecord, Paper, PaperExtractedInfo, QAMessage, TextChunk, User
from app.schemas import EvidenceMatrixIn, ResearchRadarIn
from app.utils.chunk_quality import normalize_chunk_text, normalize_page_number

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


GENERIC_EVIDENCE_PHRASES = (
    '当前解析未提取到明确证据',
    '当前解析未提取',
    '原文片段中未充分体现',
    '未单独抽取该字段',
    '可参考摘要',
    '基于公开数据集进行实验验证',
    '在公开数据集和临床超声图像上进行实验验证',
    '在两个数据集上进行定量和定性实验验证',
)


def _is_generic_extracted_snippet(text: str) -> bool:
    content = re.sub(r'\s+', ' ', (text or '').strip())
    if not content or content in {'-', '—', '–'}:
        return True
    if content.startswith('暂未') and len(content) < 80:
        return True
    if any(phrase in content for phrase in GENERIC_EVIDENCE_PHRASES):
        return len(content) <= 72
    return False


def _sanitize_section_title(section_title: str | None) -> str:
    title = (section_title or '').strip()
    if title in {'结构化抽取结果', '结构化摘要'}:
        return ''
    return title


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
    chinese_count = len(re.findall(r'[\u4e00-\u9fff]', content))
    if chinese_count >= 30 and len(content) >= 50:
        return True
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
            '研究问题', '研究目标', '本文旨在', '针对', '挑战',
        ],
        'method': [
            'we propose', 'we introduce', 'framework', 'method',
            'approach', 'pipeline', 'architecture', 'algorithm',
            'system', 'model', 'harness', 'protocol',
            '方法', '模型', '网络', '框架', '算法', '模块',
        ],
        'experiment_data': [
            'dataset', 'benchmark', 'data collection', 'tasks',
            'experimental setup', 'task setup', 'evaluation setup',
            'instances', 'samples', 'cases',
            '数据集', '实验数据', '训练集', '测试集', '样本', '超声图像',
        ],
        'metrics': [
            'metric', 'score', 'accuracy', 'precision', 'recall',
            'f1', 'auc', 'pass rate', 'evaluation', 'measure',
            '指标', 'psnr', 'ssim', 'dice', 'iou', '准确率', '召回率',
        ],
        'main_results': [
            'results', 'performance', 'outperform', 'achieves',
            'improves', 'we find', 'table', 'overall performance',
            'main results',
            '实验结果', '结果表明', '性能', '优于', '提升', '达到',
        ],
        'innovations': [
            'contribution', 'novel', 'first', 'new', 'we introduce',
            'we propose', 'innovation', 'unified', 'process-verified',
            '创新', '贡献', '首次', '提出',
        ],
        'limitations': [
            'limitation', 'threat', 'fail', 'failure', 'risk',
            'weakness', 'future work', 'cannot', 'not address',
            '局限', '不足', '限制', '失败',
        ],
        'future_work': [
            'future work', 'future direction', 'further research',
            'we plan', 'could be extended', 'next step',
            '未来工作', '进一步', '展望',
        ],
    }

    section_prefer = {
        'research_question': ['abstract', 'introduction', '摘要', '引言'],
        'method': ['method', 'approach', 'framework', 'system', 'design', '方法', '模型'],
        'experiment_data': ['dataset', 'benchmark', 'data collection', 'experimental setup', 'task setup', '数据', '实验'],
        'metrics': ['metric', 'evaluation', 'experimental setup', 'results', '指标', '评价'],
        'main_results': ['result', 'experiment', 'evaluation', 'overall performance', '结果', '实验'],
        'innovations': ['abstract', 'introduction', 'conclusion', '摘要', '结论'],
        'limitations': ['limitation', 'threat', 'discussion', 'conclusion', '讨论', '局限'],
        'future_work': ['future', 'conclusion', 'discussion', '展望', '未来'],
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


def _normalize_bbox(raw: object) -> list[float] | None:
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            nums = [float(x) for x in raw]
        except (TypeError, ValueError):
            return None
        if all(abs(x) < 1e9 for x in nums):
            return nums
    if isinstance(raw, dict):
        if all(k in raw for k in ('left', 'top', 'width', 'height')):
            left = float(raw['left'])
            top = float(raw['top'])
            width = float(raw['width'])
            height = float(raw['height'])
            return [left, top, left + width, top + height]
    return None


def _pick_locate_snippet(text: str, limit: int = 160) -> str:
    content = _normalize_snippet(text, 900)
    if len(content) <= limit:
        return content

    best = ''
    best_score = -1
    for sent in re.split(r'(?<=[。！？；;!?])\s*', content):
        piece = sent.strip()
        if len(piece) < 20:
            continue
        score = len(piece)
        score += len(re.findall(r'[\u4e00-\u9fff]', piece)) * 2
        score += len(re.findall(r'\d+\.?\d*', piece)) * 5
        if score > best_score and len(piece) <= limit:
            best_score = score
            best = piece
    if best:
        return best[:limit]

    start = max(0, (len(content) - limit) // 3)
    return content[start:start + limit]


def _locate_snippet_in_content(
    paper_id: int,
    snippet: str,
    content_by_paper: dict[int, list[ContentItem]],
    page_hint: int | None = None,
) -> tuple[int | None, list[float] | None, str]:
    needle = _normalize_snippet(snippet, 220)
    needle_lower = needle.lower()
    if len(re.sub(r'\s+', '', needle)) < 8:
        return None, None, ''

    items = content_by_paper.get(paper_id, [])
    if page_hint:
        page_items = [item for item in items if item.page_number == page_hint]
        if page_items:
            items = page_items

    best: tuple[int | None, list[float] | None, str, int] | None = None

    for item in items:
        text = (item.content or '').strip()
        if not text:
            continue
        lowered = text.lower()
        score = 0

        if needle_lower in lowered:
            score = len(needle_lower) + 1000
        else:
            for probe_len in (160, 120, 80, 48, 32):
                probe = needle_lower[:probe_len]
                if len(probe) >= 12 and probe in lowered:
                    score = probe_len
                    break
            if score <= 0:
                continue

        if page_hint and item.page_number == page_hint:
            score += 500
        if item.bbox:
            score += 20

        if best is None or score > best[3]:
            best = (item.page_number, _normalize_bbox(item.bbox), item.item_type or '', score)

    if best:
        return best[0], best[1], best[2]
    return None, None, ''


def _load_chunk_locators(
    chunk_rows: list[tuple[TextChunk, ContentItem | None]],
) -> dict[int, dict]:
    locators: dict[int, dict] = {}
    for chunk, item in chunk_rows:
        chunk_text = normalize_chunk_text(chunk.chunk_text or '')
        page_number = normalize_page_number(chunk.page_number) or normalize_page_number(
            item.page_number if item else None
        )
        locators[int(chunk.id)] = {
            'chunk_id': int(chunk.id),
            'section_id': chunk.section_id,
            'page_number': page_number,
            'bbox': _normalize_bbox(item.bbox if item else None),
            'chunk_text': chunk_text,
        }
    return locators


def _make_evidence(
    paper: Paper,
    snippet: str,
    page_number: int | None,
    section_title: str | None,
    score: float | None,
    dimension_key: str,
    bbox: object | None = None,
    content_by_paper: dict[int, list[ContentItem]] | None = None,
    chunk_id: int | None = None,
    section_id: int | None = None,
) -> dict:
    text = _normalize_snippet(snippet)
    located_page = normalize_page_number(page_number)
    located_bbox = _normalize_bbox(bbox)
    located_section = section_title or ''

    if content_by_paper is not None and not located_bbox:
        found_page, found_bbox, found_section = _locate_snippet_in_content(
            paper.id,
            text,
            content_by_paper,
            page_hint=located_page,
        )
        if found_page and not located_page:
            located_page = found_page
        if found_bbox:
            located_bbox = found_bbox
        if found_section and not located_section:
            located_section = found_section

    locate_snippet = _pick_locate_snippet(text)

    source: dict = {
        'paper_id': paper.id,
        'page_number': located_page or None,
        'section_title': located_section,
        'snippet': text,
        'paper_title': paper.title or paper.original_filename,
    }
    if chunk_id:
        source['chunk_id'] = int(chunk_id)
    if section_id:
        source['section_id'] = int(section_id)
    if located_bbox:
        source['bbox'] = located_bbox
        source['locate_type'] = 'bbox'
        source['locate_snippet'] = locate_snippet
    elif located_page:
        source['locate_type'] = 'page'
        source['locate_snippet'] = locate_snippet

    clean_section = _sanitize_section_title(located_section)

    return {
        'paper_id': paper.id,
        'paper_title': paper.title or paper.original_filename,
        'snippet': text,
        'page_number': located_page or None,
        'section_title': clean_section,
        'score': round(score, 4) if score is not None else None,
        'support': _support_from_score(score),
        'dimension_key': dimension_key,
        'source': {
            **source,
            'section_title': clean_section,
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

    chunk_rows = (
        await db.execute(
            select(TextChunk, ContentItem)
            .outerjoin(ContentItem, TextChunk.section_id == ContentItem.id)
            .where(TextChunk.paper_id.in_(paper_ids))
        )
    ).all()
    chunk_locators = _load_chunk_locators(chunk_rows)

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

                    chunk_id = c.get('chunk_id')
                    chunk_meta = chunk_locators.get(int(chunk_id)) if chunk_id is not None else None
                    if chunk_meta:
                        snippet = chunk_meta.get('chunk_text') or snippet

                    evidences.append(
                        _make_evidence(
                            paper=paper,
                            snippet=snippet,
                            page_number=(
                                chunk_meta.get('page_number')
                                if chunk_meta
                                else normalize_page_number(c.get('page_number'))
                            ),
                            section_title=section_title,
                            score=score,
                            dimension_key=dim_key,
                            bbox=chunk_meta.get('bbox') if chunk_meta else None,
                            chunk_id=int(chunk_id) if chunk_id is not None else None,
                            section_id=chunk_meta.get('section_id') if chunk_meta else None,
                            content_by_paper=content_by_paper,
                        )
                    )
                    if evidences[-1].get('support') == 'weak':
                        evidences.pop()
                        continue
                    if len(evidences) >= 2:
                        break

            if not evidences:
                for item in content_by_paper.get(paper.id, []):
                    text = (item.content or '').strip()
                    if _is_generic_extracted_snippet(text):
                        continue
                    if _is_low_quality_evidence(text, item.item_type or '', dim_key):
                        continue
                    if not _looks_like_natural_evidence(text):
                        continue
                    if not _matches_dimension(text, item.item_type or '', dim_key):
                        continue

                    normalized_key = _normalize_snippet(text, 160).lower()
                    if normalized_key in seen:
                        continue
                    seen.add(normalized_key)

                    evidences.append(
                        _make_evidence(
                            paper=paper,
                            snippet=text,
                            page_number=normalize_page_number(item.page_number),
                            section_title=item.item_type or '',
                            score=None,
                            dimension_key=dim_key,
                            bbox=item.bbox,
                            section_id=int(item.id),
                            content_by_paper=content_by_paper,
                        )
                    )
                    if len(evidences) >= 2:
                        break

            if not evidences and anchor and not _is_generic_extracted_snippet(anchor):
                anchor_page, anchor_bbox, anchor_section = _locate_snippet_in_content(
                    paper.id,
                    anchor,
                    content_by_paper,
                )
                display_snippet = ''
                display_page = anchor_page
                display_bbox = anchor_bbox
                display_section = anchor_section
                matched_item: ContentItem | None = None

                if anchor_page:
                    for item in content_by_paper.get(paper.id, []):
                        if item.page_number != anchor_page:
                            continue
                        item_text = (item.content or '').strip()
                        if not item_text or _is_generic_extracted_snippet(item_text):
                            continue
                        display_snippet = item_text
                        display_section = item.item_type or anchor_section
                        display_bbox = _normalize_bbox(item.bbox) or anchor_bbox
                        matched_item = item
                        break

                if not display_snippet and len(anchor) >= 80:
                    display_snippet = anchor

                if display_snippet and _looks_like_natural_evidence(display_snippet):
                    evidences.append(
                        _make_evidence(
                            paper=paper,
                            snippet=display_snippet,
                            page_number=normalize_page_number(display_page),
                            section_title=display_section or '',
                            score=None,
                            dimension_key=dim_key,
                            bbox=display_bbox,
                            section_id=int(matched_item.id) if matched_item else None,
                            content_by_paper=content_by_paper,
                        )
                    )

            evidences = [
                ev for ev in evidences
                if not _is_generic_extracted_snippet(ev.get('snippet', ''))
            ]

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
