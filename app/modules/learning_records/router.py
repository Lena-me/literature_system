from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import LearningRecord, Paper, QAMessage, QASession, Report, User, KnowledgeDomain, KnowledgeGraph, ComparisonResult, QAMessageSource, SubjectHierarchy
from app.schemas import LearningRecordIn
from app.utils.json_utils import dumps, loads
router = APIRouter(prefix='/learning-records', tags=['学习档案'])

@router.post('')
async def create_record(data: LearningRecordIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = LearningRecord(user_id=user.id, paper_id=data.paper_id, event_type=data.event_type, event_data=dumps(data.event_data or {}))
    db.add(obj); await db.commit(); await db.refresh(obj)
    return {'id': obj.id}

def _generate_upload_heatmap_data(db_result: list[tuple]) -> dict:
    upload_counts: dict[str, int] = {}
    for row in db_result:
        dt, count = row
        if isinstance(dt, datetime):
            dt = dt.date()
        date_str = dt.strftime('%Y-%m-%d')
        upload_counts[date_str] = int(count)

    today = date.today()
    months = []
    for i in range(11, -1, -1):
        month_start = (today - timedelta(days=i * 30)).replace(day=1)
        months.append(month_start.strftime('%Y-%m'))

    month_data: dict[str, list[int]] = {}
    for month_str in months:
        year, month = map(int, month_str.split('-'))
        days_in_month = (datetime(year, month + 1, 1) - timedelta(days=1)).day if month < 12 else 31
        month_data[month_str] = [0] * days_in_month
        for day in range(1, days_in_month + 1):
            date_str = f'{year:04d}-{month:02d}-{day:02d}'
            if date_str in upload_counts:
                month_data[month_str][day - 1] = upload_counts[date_str]

    return {
        'months': months,
        'data': month_data,
        'max_value': max(upload_counts.values(), default=1),
    }

def _calculate_streak_days(db_result: list[tuple]) -> int:
    active_dates = set()
    for row in db_result:
        dt = row[0]
        if isinstance(dt, datetime):
            dt = dt.date()
        active_dates.add(dt)

    if not active_dates:
        return 0

    today = date.today()
    streak = 0
    check_date = today

    while check_date in active_dates:
        streak += 1
        check_date -= timedelta(days=1)

    return streak


def _calculate_total_minutes(records: list[LearningRecord]) -> int:
    if len(records) < 1:
        return 0

    sorted_records = sorted(records, key=lambda r: r.created_at)
    total_seconds = 0
    gap_threshold = 10 * 60

    session_start = sorted_records[0].created_at

    for i in range(1, len(sorted_records)):
        prev_time = sorted_records[i-1].created_at
        curr_time = sorted_records[i].created_at
        diff = (curr_time - prev_time).total_seconds()

        if diff > gap_threshold:
            total_seconds += (prev_time - session_start).total_seconds()
            session_start = curr_time

    total_seconds += (sorted_records[-1].created_at - session_start).total_seconds()

    return int(total_seconds // 60)


async def _calculate_today_minutes(db: AsyncSession, user_id: int) -> int:
    from sqlalchemy import select, func
    from app.models import LearningDuration
    today = date.today()
    result = await db.execute(
        select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0))
        .where(LearningDuration.user_id == user_id, LearningDuration.record_date == today)
    )
    return result.scalar_one()


def _extract_keywords_from_papers(papers):
    keywords_by_year: dict[str, dict[str, int]] = {}
    all_keywords: dict[str, int] = {}
    for paper in papers:
        year = str(paper.upload_time.year) if paper.upload_time else '2025'
        if year not in keywords_by_year:
            keywords_by_year[year] = {}
        for raw in [paper.keywords, paper.subject_labels]:
            value = loads(raw, []) if isinstance(raw, str) else (raw or [])
            if isinstance(value, str):
                value = [x.strip() for x in value.replace('，', ',').split(',') if x.strip()]
            if isinstance(value, list):
                for item in value[:10]:
                    name = str(item).strip()
                    if name:
                        keywords_by_year[year][name] = keywords_by_year[year].get(name, 0) + 1
                        all_keywords[name] = all_keywords.get(name, 0) + 1
    if not all_keywords:
        all_keywords = {'RAG': 8, 'Agent': 6, '文献解析': 7, '知识图谱': 5, '实验复现': 4}
        keywords_by_year = {
            '2024': {'图像分割': 5, 'UNet': 4, '深度学习': 6},
            '2025': {'Transformer': 8, '注意力机制': 6, 'Foundation Models': 5, '图像分割': 3},
            '2026': {'Foundation Models': 10, '图像分割': 4, 'Transformer': 6, 'AI Agent': 5}
        }
    return keywords_by_year, all_keywords


def _generate_keyword_evolution(keywords_by_year: dict[str, dict[str, int]]):
    years = sorted(keywords_by_year.keys())
    all_keywords = set()
    for year_data in keywords_by_year.values():
        all_keywords.update(year_data.keys())

    evolution_data = []
    for keyword in sorted(all_keywords):
        data_points = []
        for year in years:
            data_points.append({
                'year': year,
                'value': keywords_by_year.get(year, {}).get(keyword, 0)
            })
        evolution_data.append({
            'keyword': keyword,
            'data': data_points
        })

    return {
        'years': years,
        'keywords': evolution_data
    }


async def _analyze_knowledge_domains(db: AsyncSession, user_id: int, total_papers: int):
    """基于 subject_hierarchy 表（LLM生成）构建知识域层级。

    使用 primary_domain / secondary_domain / tertiary_domain 三级结构。
    """
    rows = (await db.execute(
        select(
            SubjectHierarchy.primary_domain,
            SubjectHierarchy.secondary_domain,
            SubjectHierarchy.tertiary_domain,
            SubjectHierarchy.is_core,
            func.count(func.distinct(SubjectHierarchy.paper_id)).label('paper_count')
        )
        .where(SubjectHierarchy.user_id == user_id)
        .group_by(
            SubjectHierarchy.primary_domain,
            SubjectHierarchy.secondary_domain,
            SubjectHierarchy.tertiary_domain,
            SubjectHierarchy.is_core
        )
    )).all()

    if not rows:
        return {
            'count': 0,
            'top_domains': [],
            'tag_frequency': {},
            'cross_domain_rate': 0.0,
            'total_papers': 0,
            'cross_domain_papers': 0,
            'sub_domain_granularity': 0,
            'core_papers': 0,
            'non_core_papers': 0,
        }

    primary_map: dict[str, dict[str, dict[str, int]]] = {}
    primary_paper_set: dict[str, set[int]] = {}
    all_tag_freq: dict[str, int] = {}
    core_paper_ids: set[int] = set()
    non_core_paper_ids: set[int] = set()

    for row in rows:
        primary = row.primary_domain
        secondary = row.secondary_domain
        tertiary = row.tertiary_domain
        paper_count = row.paper_count
        is_core = row.is_core

        if primary not in primary_map:
            primary_map[primary] = {}
            primary_paper_set[primary] = set()

        if secondary:
            if secondary not in primary_map[primary]:
                primary_map[primary][secondary] = {}
            if tertiary:
                primary_map[primary][secondary][tertiary] = primary_map[primary][secondary].get(tertiary, 0) + paper_count
        else:
            if '其他' not in primary_map[primary]:
                primary_map[primary]['其他'] = {}

    paper_primary_rows = (await db.execute(
        select(
            SubjectHierarchy.paper_id,
            SubjectHierarchy.primary_domain,
            SubjectHierarchy.is_core
        )
        .where(SubjectHierarchy.user_id == user_id, SubjectHierarchy.paper_id.isnot(None))
        .distinct()
    )).all()

    paper_primary_map: dict[int, set[str]] = {}
    for row in paper_primary_rows:
        pid = row.paper_id
        if pid not in paper_primary_map:
            paper_primary_map[pid] = set()
        paper_primary_map[pid].add(row.primary_domain)
        if row.is_core:
            core_paper_ids.add(pid)
        else:
            non_core_paper_ids.add(pid)

    labeled_paper_ids = set(paper_primary_map.keys())
    total_labeled_papers = len(labeled_paper_ids)

    primary_freq = {}
    for pid, primaries in paper_primary_map.items():
        for p in primaries:
            primary_paper_set.setdefault(p, set()).add(pid)
            primary_freq[p] = len(primary_paper_set[p])

    for primary, secondaries in primary_map.items():
        all_tag_freq[primary] = primary_freq.get(primary, 0)
        for secondary, tertiaries in secondaries.items():
            sec_freq = sum(tertiaries.values()) if tertiaries else 0
            if sec_freq > 0:
                all_tag_freq[secondary] = all_tag_freq.get(secondary, 0) + sec_freq
            for tertiary, freq in tertiaries.items():
                all_tag_freq[tertiary] = all_tag_freq.get(tertiary, 0) + freq

    top_domains_list = []
    for primary, secondaries in primary_map.items():
        sub_domains = []
        for secondary, tertiaries in sorted(
            secondaries.items(),
            key=lambda x: -sum(x[1].values()) if x[1] else 0
        ):
            sub_domains.append({
                'name': secondary,
                'frequency': sum(tertiaries.values()) if tertiaries else 0,
                'tertiary_count': len(tertiaries) if tertiaries else 0,
            })

        top_domains_list.append({
            'name': primary,
            'frequency': primary_freq.get(primary, 0),
            'sub_domains': sub_domains,
            'sub_domain_count': len(sub_domains),
        })

    top_domains_list.sort(key=lambda d: -d['frequency'])

    if total_labeled_papers > 0:
        multi_primary_papers = sum(
            1 for pid, primaries in paper_primary_map.items()
            if len(primaries) > 1
        )
        cross_domain_rate = multi_primary_papers / total_labeled_papers
    else:
        multi_primary_papers = 0
        cross_domain_rate = 0.0

    sub_domain_granularity = sum(d['sub_domain_count'] for d in top_domains_list)

    return {
        'count': len(top_domains_list),
        'top_domains': top_domains_list,
        'tag_frequency': all_tag_freq,
        'cross_domain_rate': round(cross_domain_rate, 4),
        'total_papers': total_labeled_papers,
        'cross_domain_papers': multi_primary_papers,
        'sub_domain_granularity': sub_domain_granularity,
        'core_papers': len(core_paper_ids),
        'non_core_papers': len(non_core_paper_ids),
    }


@router.get('/overview')
async def overview(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    paper_count = (await db.execute(select(func.count()).select_from(Paper).where(Paper.user_id == user.id, Paper.is_deleted == False))).scalar_one()
    report_count = (await db.execute(select(func.count()).select_from(Report).where(Report.user_id == user.id))).scalar_one()
    qa_count = (await db.execute(select(func.count()).select_from(QAMessage).join(QASession, QAMessage.session_id == QASession.id).where(QASession.user_id == user.id, QAMessage.role == 'user'))).scalar_one()
    records = (await db.execute(select(LearningRecord).where(LearningRecord.user_id == user.id).order_by(LearningRecord.created_at.desc()))).scalars().all()
    papers = (await db.execute(select(Paper).where(Paper.user_id == user.id, Paper.is_deleted == False).order_by(Paper.upload_time.desc()).limit(200))).scalars().all()

    keywords_by_year, keyword_cloud = _extract_keywords_from_papers(papers)
    keyword_evolution = _generate_keyword_evolution(keywords_by_year)

    knowledge_domains_analysis = await _analyze_knowledge_domains(db, user.id, paper_count)

    graph_count = (await db.execute(select(func.count()).select_from(KnowledgeGraph).where(KnowledgeGraph.user_id == user.id))).scalar_one()
    comparison_count = (await db.execute(select(func.count()).select_from(ComparisonResult).where(ComparisonResult.user_id == user.id))).scalar_one()

    unique_paper_sources = (await db.execute(
        select(func.count(func.distinct(QAMessageSource.paper_id)))
        .join(QAMessage, QAMessageSource.message_id == QAMessage.id)
        .join(QASession, QAMessage.session_id == QASession.id)
        .where(QASession.user_id == user.id)
    )).scalar_one() or 0

    today = date.today()
    one_year_ago = today - timedelta(days=365)
    upload_stats = (await db.execute(
        select(func.date(Paper.upload_time), func.count())
        .where(Paper.user_id == user.id, Paper.is_deleted == False, Paper.upload_time >= one_year_ago)
        .group_by(func.date(Paper.upload_time))
    )).all()
    heatmap_data = _generate_upload_heatmap_data(upload_stats)

    active_dates = (await db.execute(
        select(func.date(LearningRecord.created_at))
        .where(LearningRecord.user_id == user.id)
        .group_by(func.date(LearningRecord.created_at))
    )).all()
    streak_days = _calculate_streak_days(active_dates)
    total_minutes = _calculate_total_minutes(list(records))
    today_minutes = await _calculate_today_minutes(db, user.id)

    recommended_domain = '知识增强网络'
    existing_domain_names = set(knowledge_domains_analysis.get('tag_frequency', {}).keys())
    suggestions = ['知识增强网络', '多模态学习', '图神经网络', '因果推理', '持续学习', '联邦学习', '可解释AI']
    for s in suggestions:
        if s not in existing_domain_names:
            recommended_domain = s
            break

    record_items = [{'id': r.id, 'paper_id': r.paper_id, 'event_type': r.event_type, 'event_data': loads(r.event_data,{}), 'created_at': r.created_at} for r in records]
    return {
        'paper_count': paper_count,
        'report_count': report_count,
        'qa_count': qa_count,
        'records': record_items,
        'recent_records': record_items,
        'keyword_cloud': keyword_cloud,
        'upload_heatmap': heatmap_data,
        'streak_days': streak_days,
        'total_minutes': total_minutes,
        'today_minutes': today_minutes,
        'knowledge_domains': knowledge_domains_analysis,
        'deep_research_outputs': {
            'reports': report_count,
            'comparisons': comparison_count,
            'graphs': graph_count
        },
        'question_traceability': {
            'unique_paper_sources': unique_paper_sources
        },
        'keyword_evolution': keyword_evolution,
        'recommended_domain': recommended_domain
    }
