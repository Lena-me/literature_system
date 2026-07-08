from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import LearningRecord, Paper, QAMessage, QASession, Report, User, KnowledgeDomain, KnowledgeGraph, ComparisonResult, QAMessageSource, SubjectHierarchy, LearningDuration
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

def _generate_focus_heatmap_data(db_result: list[tuple]) -> dict:
    focus_counts: dict[str, int] = {}
    for row in db_result:
        dt, minutes = row
        if isinstance(dt, datetime):
            dt = dt.date()
        date_str = dt.strftime('%Y-%m-%d')
        focus_counts[date_str] = int(minutes)

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
            if date_str in focus_counts:
                month_data[month_str][day - 1] = focus_counts[date_str]

    return {
        'months': months,
        'data': month_data,
        'max_value': max(focus_counts.values(), default=1),
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
            # 新增：专门给前端星盘使用的跨学科原始数据
            'cross_sub_items': []
        }
    primary_map: dict[str, dict[str, dict[str, int]]] = {}
    primary_paper_set: dict[str, set[int]] = {}
    all_tag_freq: dict[str, int] = {}
    core_paper_ids: set[int] = set()
    non_core_paper_ids: set[int] = set()
    all_rows = list(rows)
    primary_domain_set = set(row.primary_domain for row in all_rows)

    # 获取每篇文献的标题，用于星盘节点悬停展示
    paper_detail_rows = (await db.execute(
        select(
            SubjectHierarchy.primary_domain,
            SubjectHierarchy.secondary_domain,
            SubjectHierarchy.tertiary_domain,
            Paper.id,
            func.coalesce(Paper.title, Paper.original_filename).label('paper_title')
        )
        .join(Paper, SubjectHierarchy.paper_id == Paper.id)
        .where(SubjectHierarchy.user_id == user_id, SubjectHierarchy.paper_id.isnot(None))
        .distinct()
    )).all()
    # secondary → 文献标题列表
    sec_papers: dict[str, list[str]] = {}
    # full path (primary · secondary · tertiary 或 primary · secondary) → 文献标题列表
    leaf_papers: dict[str, list[str]] = {}
    for pd in paper_detail_rows:
        if pd.secondary_domain and pd.secondary_domain != 'None' and pd.secondary_domain.strip():
            sec_papers.setdefault(pd.secondary_domain, []).append(pd.paper_title)
            leaf_key = pd.primary_domain + ' · ' + pd.secondary_domain
            if pd.tertiary_domain and pd.tertiary_domain != 'None' and pd.tertiary_domain.strip():
                leaf_key += ' · ' + pd.tertiary_domain
        else:
            # primary-only：key 格式为 "primary · primary" 以匹配 valid_leaves 命名
            leaf_key = pd.primary_domain + ' · ' + pd.primary_domain
        leaf_papers.setdefault(leaf_key, []).append(pd.paper_title)

    primary_freq_pre: dict[str, int] = {}
    for row in all_rows:
        primary = row.primary_domain
        primary_freq_pre[primary] = primary_freq_pre.get(primary, 0) + row.paper_count

    for row in all_rows:
        primary = row.primary_domain
        secondary = row.secondary_domain
        tertiary = row.tertiary_domain
        paper_count = row.paper_count
        is_core = row.is_core
        if primary not in primary_map:
            primary_map[primary] = {}
            primary_paper_set[primary] = set()
        leaf = None
        if tertiary and tertiary != 'None' and tertiary.strip():
            leaf = tertiary
        elif secondary and secondary != 'None' and secondary.strip():
            leaf = secondary
        else:
            leaf = primary

        if leaf == primary:
            domain_total = primary_freq_pre.get(primary, 0)
            if domain_total > 2:
                continue

        if leaf not in primary_map[primary]:
            primary_map[primary][leaf] = {'_self': 0}
        primary_map[primary][leaf]['_self'] = primary_map[primary][leaf].get('_self', 0) + paper_count
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
                if tertiary != '_self':
                    all_tag_freq[tertiary] = all_tag_freq.get(tertiary, 0) + freq
    top_domains_list = []
    small_domains = []
    cross_sub_items = []  # 存储前端星盘渲染原始数据
    for primary, secondaries in primary_map.items():
        domain_total = primary_freq.get(primary, 0)
        sub_domains = []
        valid_leaves = []
        for secondary, tertiaries in sorted(
            secondaries.items(),
            key=lambda x: -sum(x[1].values()) if x[1] else 0
        ):
            valid_tertiaries = {k: v for k, v in tertiaries.items() if k != '_self'}
            total_sec = sum(tertiaries.values())
            sub_domains.append({
                'name': secondary,
                'frequency': total_sec,
                'tertiary_count': len(valid_tertiaries) if valid_tertiaries else 0,
                'papers': sec_papers.get(secondary, [])[:5],
            })
            # 收集叶子节点用于跨学科星盘
            if valid_tertiaries:
                for t_name, t_cnt in valid_tertiaries.items():
                    leaf_name = f"{primary} · {secondary} · {t_name}"
                    valid_leaves.append({
                        'origin_primary': primary,
                        'name': leaf_name,
                        'frequency': t_cnt,
                        'papers': leaf_papers.get(leaf_name, [])[:5],
                    })
            else:
                leaf_name = f"{primary} · {secondary}"
                valid_leaves.append({
                    'origin_primary': primary,
                    'name': leaf_name,
                    'frequency': total_sec,
                    'papers': leaf_papers.get(leaf_name, [])[:5],
                })
        # 判断大类阈值区分主领域/长尾跨学科
        domain_item = {
            'name': primary,
            'frequency': domain_total,
            'sub_domains': sub_domains,
            'sub_domain_count': len(sub_domains),
            '_leaves': valid_leaves
        }
        if domain_total <= 2:
            small_domains.append(domain_item)
        else:
            top_domains_list.append(domain_item)
    # 合并所有长尾领域叶子到跨学科星盘数据源
    for small in small_domains:
        cross_sub_items.extend(small['_leaves'])

    # 组装跨学科虚拟大类 —— 节点直接使用叶子节点（可以是 primary/secondary/tertiary 级叶子）
    if small_domains:
        all_leaves = []
        for d in small_domains:
            all_leaves.extend(d['_leaves'])

        short_name_counter: dict[str, int] = {}
        for leaf in all_leaves:
            short = leaf['name'].split(' · ')[-1]
            short_name_counter[short] = short_name_counter.get(short, 0) + 1

        interdisciplinary_sub_domains = []
        for leaf in all_leaves:
            short = leaf['name'].split(' · ')[-1]
            if short_name_counter[short] > 1:
                display_name = f"{leaf['origin_primary']} · {short}"
            else:
                display_name = short
            interdisciplinary_sub_domains.append({
                'name': display_name,
                'frequency': leaf['frequency'],
                'tertiary_count': 0,
                'papers': leaf.get('papers', [])[:5],
            })

        # 清理临时字段 _leaves
        for d in top_domains_list:
            d.pop('_leaves', None)
        for d in small_domains:
            d.pop('_leaves', None)

        top_domains_list.append({
            'name': '其他学科领域',
            'frequency': sum(d['frequency'] for d in small_domains),
            'sub_domains': interdisciplinary_sub_domains,
            'sub_domain_count': len(interdisciplinary_sub_domains),
            'is_interdisciplinary': True,
        })
    else:
        for d in top_domains_list:
            d.pop('_leaves', None)
        for d in small_domains:
            d.pop('_leaves', None)
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
    core_paper_ids = set(pid for pid, primaries in paper_primary_map.items() for p in primaries if any(r.is_core for r in paper_primary_rows if r.paper_id == pid))
    non_core_paper_ids = set(paper_primary_map.keys()) - core_paper_ids
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
        'cross_sub_items': cross_sub_items  # 前端星盘专用原始数据 [{name, frequency}]
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

    focus_stats = (await db.execute(
        select(LearningDuration.record_date, func.sum(LearningDuration.duration_minutes))
        .where(LearningDuration.user_id == user.id, LearningDuration.record_date >= one_year_ago)
        .group_by(LearningDuration.record_date)
    )).all()
    focus_heatmap_data = _generate_focus_heatmap_data(focus_stats)

    active_dates = (await db.execute(
        select(func.date(LearningRecord.created_at))
        .where(LearningRecord.user_id == user.id)
        .group_by(func.date(LearningRecord.created_at))
    )).all()
    streak_days = _calculate_streak_days(active_dates)
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
        'focus_heatmap': focus_heatmap_data,
        'streak_days': streak_days,
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
        'recommended_domain': recommended_domain,
        'research_interests': [kw for kw, _ in sorted(keyword_cloud.items(), key=lambda x: -x[1])[:3]]
    }


@router.get('/monthly-report')
async def monthly_report(month: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """生成月度科研学习报告，聚合本月上传文献、报告、知识图谱、问答数据，调用LLM生成AI总结"""
    from app.integrations.llm.openai_compatible import OpenAICompatibleLLM

    try:
        year, m = map(int, month.split('-'))
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(400, '月份格式错误，应为 YYYY-MM')

    month_start = datetime(year, m, 1)
    if m == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, m + 1, 1)

    # 1. 本月上传文献
    papers = (await db.execute(
        select(Paper).where(
            Paper.user_id == user.id,
            Paper.is_deleted == False,
            Paper.upload_time >= month_start,
            Paper.upload_time < month_end
        ).order_by(Paper.upload_time.desc())
    )).scalars().all()
    paper_count = len(papers)

    # 2. 本月研读报告
    reports = (await db.execute(
        select(Report).where(
            Report.user_id == user.id,
            Report.created_at >= month_start,
            Report.created_at < month_end
        ).order_by(Report.created_at.desc())
    )).scalars().all()
    report_count = len(reports)

    # 3. 本月知识图谱
    graph_count = (await db.execute(
        select(func.count()).select_from(KnowledgeGraph).where(
            KnowledgeGraph.user_id == user.id,
            KnowledgeGraph.created_at >= month_start,
            KnowledgeGraph.created_at < month_end
        )
    )).scalar_one()

    # 4. 本月AI问答
    qa_count = (await db.execute(
        select(func.count()).select_from(QAMessage).join(
            QASession, QAMessage.session_id == QASession.id
        ).where(
            QASession.user_id == user.id,
            QAMessage.role == 'user',
            QAMessage.created_at >= month_start,
            QAMessage.created_at < month_end
        )
    )).scalar_one()

    # 5. 本月对比分析
    comparison_count = (await db.execute(
        select(func.count()).select_from(ComparisonResult).where(
            ComparisonResult.user_id == user.id,
            ComparisonResult.created_at >= month_start,
            ComparisonResult.created_at < month_end
        )
    )).scalar_one()

    # 6. 专注时长
    from app.models import LearningDuration
    focus_minutes = (await db.execute(
        select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0))
        .where(
            LearningDuration.user_id == user.id,
            LearningDuration.record_date >= month_start.date(),
            LearningDuration.record_date < month_end.date()
        )
    )).scalar_one()

    # 7. 文献关键词
    keywords_by_year, keyword_cloud = _extract_keywords_from_papers(papers)
    top_keywords = [kw for kw, _ in sorted(keyword_cloud.items(), key=lambda x: -x[1])[:8]]

    # 8. 论文标题列表
    paper_titles = [p.title for p in papers[:20] if p.title]

    # 构建LLM请求数据
    data_context = f"""本月数据概览（{month}）：
- 上传文献：{paper_count} 篇
- 研读报告：{report_count} 份
- 知识图谱：{graph_count} 个
- AI问答：{qa_count} 次
- 对比分析：{comparison_count} 次
- 专注学习时长：{focus_minutes} 分钟
- 高频关键词：{', '.join(top_keywords) if top_keywords else '无'}
- 文献列表：{', '.join(paper_titles[:10]) if paper_titles else '无'}"""

    prompt = f"""角色：你是一位有10年经验的科研导师，擅长从学习数据中提炼洞察，风格是「数据驱动、温和鞭策」。

## 用户本月学习数据

{data_context}

## 输出要求

1. 结构：严格分三段，每段带小标题（使用 ## 格式）
2. 长度：总字数 600-900 字，每段 200-300 字
3. 语气：70% 客观分析 + 30% 鼓励，避免空洞表扬，具体指出进步点
4. 必须引用具体数据（如「本月上传 {paper_count} 篇文献，其中 {report_count} 份已完成研读报告」），禁止泛泛而谈

## 内容要求

### 一、研究重心演进
基于高频关键词和文献列表，梳理本月的研究主题变化，指出是否出现方向聚焦或发散。如果文献数量少于 3 篇，明确说明「文献数据不足，趋势分析仅供参考」。

### 二、知识盲区与问答复盘
基于问答次数和对比分析次数，评估知识掌握程度。如果问答次数少于 5 次，明确说明「问答数据不足，无法精准定位知识盲区」。结合关键词给出可能需要加强的方向。

### 三、下月规划建议
基于当前进度，给出 2-3 条具体可执行的文献研读建议，每条标注优先级（高/中）。建议要具体到领域方向，不要空泛。

## 重要约束
- 数据不足的部分必须明确说明，禁止编造数据
- 所有结论必须有数据支撑
- 鼓励要具体，不要用「你很棒」这种空话
- 用第二人称「你」来称呼用户"""

    try:
        llm = OpenAICompatibleLLM(scenario='monthly_report')
        generated = await llm.async_chat(
            [
                {'role': 'system', 'content': '你是一位有10年经验的科研导师，擅长从学习数据中提炼洞察，风格是「数据驱动、温和鞭策」。你只根据用户提供的真实数据进行分析，绝不编造不存在的信息。'},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.3,
            max_tokens=3000,
        )
        generated = generated.strip()
    except Exception as e:
        generated = f'AI 总结生成失败：{str(e)}，请稍后重试。'

    return {
        'month': month,
        'paper_count': paper_count,
        'report_count': report_count,
        'graph_count': graph_count,
        'qa_count': qa_count,
        'comparison_count': comparison_count,
        'focus_minutes': focus_minutes,
        'paper_titles': paper_titles[:10],
        'summary': generated,
    }
