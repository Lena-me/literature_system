from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.models import (
    ComparisonResult,
    KnowledgeGraph,
    LearningDuration,
    LearningRecord,
    Paper,
    QAMessage,
    QASession,
    Report,
    SubjectHierarchy,
    User,
)
from app.utils.json_utils import dumps, loads

GUIDANCE_EVENT_TYPE = 'research_guidance'


def _parse_month(period: str) -> tuple[datetime, datetime]:
    year, month = map(int, period.split('-'))
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def _clip_text(text: str | None, limit: int = 120) -> str:
    if not text:
        return ''
    cleaned = ' '.join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + '…'


async def _get_stored_guidance(
    db: AsyncSession,
    user_id: int,
    period_type: str,
    period: str,
) -> tuple[LearningRecord | None, dict[str, Any] | None]:
    rows = (
        await db.execute(
            select(LearningRecord)
            .where(
                LearningRecord.user_id == user_id,
                LearningRecord.event_type == GUIDANCE_EVENT_TYPE,
            )
            .order_by(LearningRecord.created_at.desc())
            .limit(80)
        )
    ).scalars().all()
    for row in rows:
        data = loads(row.event_data or '{}')
        if data.get('period_type') == period_type and data.get('period') == period:
            return row, data
    return None, None


async def _save_guidance(
    db: AsyncSession,
    user_id: int,
    period_type: str,
    period: str,
    summary: str,
    metrics: dict[str, Any],
) -> LearningRecord:
    existing, data = await _get_stored_guidance(db, user_id, period_type, period)
    payload = {
        'period_type': period_type,
        'period': period,
        'summary': summary,
        'metrics': metrics,
        'generated_at': datetime.utcnow().isoformat(),
    }
    if existing:
        existing.event_data = dumps(payload)
        existing.created_at = datetime.utcnow()
        await db.commit()
        await db.refresh(existing)
        return existing

    obj = LearningRecord(
        user_id=user_id,
        paper_id=None,
        event_type=GUIDANCE_EVENT_TYPE,
        event_data=dumps(payload),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def _collect_activity_snapshot(
    db: AsyncSession,
    user_id: int,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    papers = (
        await db.execute(
            select(Paper)
            .where(
                Paper.user_id == user_id,
                Paper.is_deleted == False,
                Paper.upload_time >= start,
                Paper.upload_time < end,
            )
            .order_by(Paper.upload_time.desc())
        )
    ).scalars().all()

    reports = (
        await db.execute(
            select(Report)
            .where(
                Report.user_id == user_id,
                Report.created_at >= start,
                Report.created_at < end,
            )
            .order_by(Report.created_at.desc())
        )
    ).scalars().all()

    graph_count = (
        await db.execute(
            select(func.count())
            .select_from(KnowledgeGraph)
            .where(
                KnowledgeGraph.user_id == user_id,
                KnowledgeGraph.created_at >= start,
                KnowledgeGraph.created_at < end,
            )
        )
    ).scalar_one()

    comparison_count = (
        await db.execute(
            select(func.count())
            .select_from(ComparisonResult)
            .where(
                ComparisonResult.user_id == user_id,
                ComparisonResult.created_at >= start,
                ComparisonResult.created_at < end,
            )
        )
    ).scalar_one()

    qa_rows = (
        await db.execute(
            select(QAMessage.content, QASession.title, QAMessage.created_at)
            .join(QASession, QAMessage.session_id == QASession.id)
            .where(
                QASession.user_id == user_id,
                QAMessage.role == 'user',
                QAMessage.created_at >= start,
                QAMessage.created_at < end,
            )
            .order_by(QAMessage.created_at.desc())
            .limit(12)
        )
    ).all()

    learning_events = (
        await db.execute(
            select(LearningRecord)
            .where(
                LearningRecord.user_id == user_id,
                LearningRecord.created_at >= start,
                LearningRecord.created_at < end,
                LearningRecord.event_type.in_(
                    ['ai_message', 'paper_open', 'paper_read', 'paper_upload', 'generate_report', 'generate_kg']
                ),
            )
            .order_by(LearningRecord.created_at.desc())
            .limit(30)
        )
    ).scalars().all()

    focus_minutes = (
        await db.execute(
            select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0)).where(
                LearningDuration.user_id == user_id,
                LearningDuration.record_date >= start.date(),
                LearningDuration.record_date < end.date(),
            )
        )
    ).scalar_one()

    paper_ids = [p.id for p in papers]
    domain_rows = []
    if paper_ids:
        domain_rows = (
            await db.execute(
                select(
                    SubjectHierarchy.primary_domain,
                    SubjectHierarchy.secondary_domain,
                    func.count(func.distinct(SubjectHierarchy.paper_id)).label('paper_count'),
                )
                .where(
                    SubjectHierarchy.user_id == user_id,
                    SubjectHierarchy.paper_id.in_(paper_ids),
                )
                .group_by(SubjectHierarchy.primary_domain, SubjectHierarchy.secondary_domain)
                .order_by(func.count(func.distinct(SubjectHierarchy.paper_id)).desc())
                .limit(6)
            )
        ).all()

    keywords: dict[str, int] = {}
    for paper in papers:
        for raw in [paper.keywords, paper.subject_labels]:
            value = loads(raw, []) if isinstance(raw, str) else (raw or [])
            if isinstance(value, str):
                value = [x.strip() for x in value.replace('，', ',').split(',') if x.strip()]
            if isinstance(value, list):
                for item in value[:8]:
                    name = str(item).strip()
                    if name:
                        keywords[name] = keywords.get(name, 0) + 1

    top_keywords = [kw for kw, _ in sorted(keywords.items(), key=lambda x: -x[1])[:8]]
    paper_titles = [_clip_text(p.title or p.original_filename, 80) for p in papers[:12] if (p.title or p.original_filename)]
    report_titles = [_clip_text(r.title, 80) for r in reports[:8] if r.title]

    qa_questions = []
    for content, session_title, _created_at in qa_rows:
        text = _clip_text(content, 160)
        if text:
            qa_questions.append({'question': text, 'session': _clip_text(session_title, 40) or '未命名对话'})

    notebook_questions = []
    recent_actions: list[str] = []
    for event in learning_events:
        data = loads(event.event_data or '{}')
        if event.event_type == 'ai_message':
            question = _clip_text(data.get('question') or data.get('content'), 160)
            if question:
                notebook_questions.append(question)
        elif event.event_type == 'paper_upload':
            recent_actions.append(f"上传文献《{_clip_text(data.get('filename'), 60)}》")
        elif event.event_type == 'paper_open':
            recent_actions.append('打开文献阅读')
        elif event.event_type == 'paper_read':
            page = data.get('page')
            recent_actions.append(f'阅读至第 {page} 页' if page else '持续阅读文献')
        elif event.event_type == 'generate_report':
            recent_actions.append('生成研读报告')
        elif event.event_type == 'generate_kg':
            recent_actions.append('构建知识图谱')

    all_questions = []
    seen = set()
    for item in qa_questions:
        q = item['question']
        if q not in seen:
            seen.add(q)
            all_questions.append(item)
    for q in notebook_questions:
        if q not in seen:
            seen.add(q)
            all_questions.append({'question': q, 'session': '学习笔记'})

    domain_lines = []
    for row in domain_rows:
        secondary = row.secondary_domain if row.secondary_domain and row.secondary_domain != 'None' else ''
        label = f'{row.primary_domain} · {secondary}' if secondary else row.primary_domain
        domain_lines.append(f'{label}（{row.paper_count} 篇）')

    return {
        'paper_count': len(papers),
        'report_count': len(reports),
        'graph_count': int(graph_count or 0),
        'qa_count': len(qa_rows),
        'comparison_count': int(comparison_count or 0),
        'focus_minutes': int(focus_minutes or 0),
        'paper_titles': paper_titles,
        'report_titles': report_titles,
        'top_keywords': top_keywords,
        'questions': all_questions[:10],
        'recent_actions': recent_actions[:8],
        'domain_lines': domain_lines,
    }


def _format_monthly_writing_brief(period: str, snapshot: dict[str, Any]) -> str:
    """将统计数据整理为供模型内化的叙事素材，避免清单式复述。"""
    papers = [_clip_text(t, 40) for t in snapshot['paper_titles'][:3]]
    questions = [_clip_text(item['question'], 90) for item in snapshot['questions'][:4]]
    keywords = snapshot['top_keywords'][:5]

    lines = [
        f'月份：{period}',
        (
            f'本月约 {snapshot["paper_count"]} 篇文献、{snapshot["report_count"]} 份研读报告、'
            f'{snapshot["graph_count"]} 个知识图谱，专注约 {snapshot["focus_minutes"]} 分钟'
        ),
    ]
    if keywords:
        lines.append(f'反复出现的主题：{"、".join(keywords)}')
    if papers:
        lines.append(f'读过的文献（举例，勿全文罗列）：{"；".join(papers)}')
    if questions:
        lines.append(f'问过的问题（举例，勿照抄）：{"；".join(questions)}')
    elif snapshot.get('qa_count', 0) > 0:
        lines.append(f'本月有 {snapshot["qa_count"]} 次问答，具体问句未全部收录')
    return '\n'.join(lines)


def _build_monthly_prompt(period: str, snapshot: dict[str, Any]) -> str:
    brief = _format_monthly_writing_brief(period, snapshot)

    return f"""请根据下方「写作素材」生成一条学习档案 App 内的「本月学习小结」温馨提示。

【写作素材（仅供你内化理解，禁止逐条复述或堆砌）】
{brief}

【好示范（学习这种语感，不要照抄内容）】
这个月你的注意力明显往超声分割上收了——SegFormer 和医学超声那几篇不是随便翻翻，而是在找能落地的方法。提问也从「是什么」转向「怎么跑通」，说明开始认真卡技术细节了。下个月先把 U-Net 的编解码结构啃透，再拿一个小数据集把分割 baseline 跑出来，会比继续泛读更有效。

【坏示范（严禁写成这样）】
❌ 「在2026年7月的学习过程中，你积极研读了13篇文献……」
❌ 「诸如《……》和《……》都体现了你对前沿技术的关注」
❌ 「你的高频关键词如……显示出……然而从典型思考片段来看……」
❌ 「希望这些建议能为你的学习之路提供实质性帮助」
❌ 把文献标题、关键词、问题用顿号或分号串成清单

【撰写要求】
1. 输出一整段，220-300 字，2-3 个自然段，段落之间用换行分隔。
2. 像 App 里的月度回顾卡片：口语化、有判断、有温度，用「你」称呼用户。
3. 只挑 1-2 个最有代表性的文献或问题自然带入，其余用「超声分割」「深度学习」等概括，禁止目录式罗列。
4. 说清楚本月主线（更聚焦还是更发散）和 1 个真实卡点，再给 1-2 条下个月能直接动手的建议。
5. 禁止：书信体、导师自称、编号标题、总结套话（「综上所述」「希望对你有帮助」）、复述素材里的字段名（如「典型思考片段」「高频关键词」）。
6. 必须基于素材中的真实信息，禁止编造未出现的文献名或概念。"""


_SYSTEM_PROMPTS = {
    'monthly': (
        '你是学习档案 App 的「本月学习小结」文案模块。你把学习数据写成简短、好读的回顾卡片，'
        '像朋友在帮你复盘这个月，而不是写汇报或评语。'
        '禁止公文腔（在……过程中、诸如、体现了、显示出、综上所述）、禁止清单式罗列、'
        '禁止套话结尾（希望对你有帮助）。只使用用户数据中真实出现的信息。'
    ),
    'dashboard': (
        '你是学习档案 App 工作台 Banner 的文案。'
        '你只输出一句话：像懂你的熟人轻轻点你一下，有人情味、口语、有温度。'
        '禁止两句及以上、禁止分号、禁止功能说明书口吻、禁止套话。'
        '只使用用户数据中真实出现的信息。'
    ),
}


async def _generate_summary(prompt: str, period_type: str = 'monthly') -> str:
    try:
        llm = OpenAICompatibleLLM(scenario='monthly_report')
        system_content = _SYSTEM_PROMPTS.get(period_type, _SYSTEM_PROMPTS['monthly'])
        # temperature / max_tokens 不传，走管理后台「月度报告总结」场景的配置
        generated = await llm.async_chat(
            [
                {'role': 'system', 'content': system_content},
                {'role': 'user', 'content': prompt},
            ],
        )
        return generated.strip()
    except Exception as e:
        return f'AI 总结生成失败：{str(e)}，请稍后重试。'


def _build_response(
    period_type: str,
    period: str,
    summary: str,
    snapshot: dict[str, Any],
    cached: bool,
    generated_at: str | None,
) -> dict[str, Any]:
    base = {
        'period_type': period_type,
        'period': period,
        'summary': summary,
        'cached': cached,
        'generated_at': generated_at,
        'paper_count': snapshot['paper_count'],
        'report_count': snapshot['report_count'],
        'graph_count': snapshot['graph_count'],
        'qa_count': snapshot['qa_count'],
        'comparison_count': snapshot['comparison_count'],
        'focus_minutes': snapshot['focus_minutes'],
        'paper_titles': snapshot['paper_titles'][:10],
        'questions': snapshot['questions'],
    }
    if period_type == 'monthly':
        base['month'] = period
    return base


async def get_or_generate_guidance(
    db: AsyncSession,
    user: User,
    period_type: str,
    period: str,
    force: bool = False,
) -> dict[str, Any]:
    if period_type != 'monthly':
        raise ValueError('仅支持 monthly 类型')

    start, end = _parse_month(period)

    if not force:
        _row, stored = await _get_stored_guidance(db, user.id, period_type, period)
        if stored and stored.get('summary'):
            metrics = stored.get('metrics') or {}
            return _build_response(
                period_type,
                period,
                stored['summary'],
                metrics,
                cached=True,
                generated_at=stored.get('generated_at'),
            )

    snapshot = await _collect_activity_snapshot(db, user.id, start, end)
    prompt = _build_monthly_prompt(period, snapshot)
    summary = await _generate_summary(prompt, 'monthly')
    record = await _save_guidance(db, user.id, period_type, period, summary, snapshot)
    stored_data = loads(record.event_data or '{}')
    return _build_response(
        period_type,
        period,
        summary,
        snapshot,
        cached=False,
        generated_at=stored_data.get('generated_at'),
    )


async def _collect_dashboard_context(db: AsyncSession, user_id: int) -> dict[str, Any]:
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    today_end = today_start + timedelta(days=1)
    week_start = today_start - timedelta(days=7)

    total_papers = (
        await db.execute(
            select(func.count()).select_from(Paper).where(
                Paper.user_id == user_id,
                Paper.is_deleted == False,
            )
        )
    ).scalar_one()

    parsed_papers = (
        await db.execute(
            select(func.count()).select_from(Paper).where(
                Paper.user_id == user_id,
                Paper.is_deleted == False,
                Paper.parse_status.in_(['completed', 'indexed']),
            )
        )
    ).scalar_one()

    papers = (
        await db.execute(
            select(Paper)
            .where(Paper.user_id == user_id, Paper.is_deleted == False)
            .order_by(Paper.upload_time.desc())
            .limit(8)
        )
    ).scalars().all()

    graphs = (
        await db.execute(
            select(KnowledgeGraph)
            .where(KnowledgeGraph.user_id == user_id)
            .order_by(KnowledgeGraph.created_at.desc())
            .limit(3)
        )
    ).scalars().all()

    graph_count = (
        await db.execute(
            select(func.count()).select_from(KnowledgeGraph).where(KnowledgeGraph.user_id == user_id)
        )
    ).scalar_one()

    session_count = (
        await db.execute(
            select(func.count()).select_from(QASession).where(QASession.user_id == user_id)
        )
    ).scalar_one()

    report_count = (
        await db.execute(
            select(func.count()).select_from(Report).where(Report.user_id == user_id)
        )
    ).scalar_one()

    recent_questions = (
        await db.execute(
            select(QAMessage.content)
            .join(QASession, QAMessage.session_id == QASession.id)
            .where(
                QASession.user_id == user_id,
                QAMessage.role == 'user',
                QAMessage.created_at >= week_start,
            )
            .order_by(QAMessage.created_at.desc())
            .limit(3)
        )
    ).scalars().all()

    learning_events = (
        await db.execute(
            select(LearningRecord)
            .where(
                LearningRecord.user_id == user_id,
                LearningRecord.created_at >= week_start,
                LearningRecord.event_type.in_(['paper_open', 'paper_read', 'ai_message', 'paper_upload']),
            )
            .order_by(LearningRecord.created_at.desc())
            .limit(8)
        )
    ).scalars().all()

    today_focus = (
        await db.execute(
            select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0)).where(
                LearningDuration.user_id == user_id,
                LearningDuration.record_date >= today_start.date(),
                LearningDuration.record_date < today_end.date(),
            )
        )
    ).scalar_one()

    keywords: dict[str, int] = {}
    for paper in papers:
        for raw in [paper.keywords, paper.subject_labels]:
            value = loads(raw, []) if isinstance(raw, str) else (raw or [])
            if isinstance(value, str):
                value = [x.strip() for x in value.replace('，', ',').split(',') if x.strip()]
            if isinstance(value, list):
                for item in value[:5]:
                    name = str(item).strip()
                    if name:
                        keywords[name] = keywords.get(name, 0) + 1

    recent_actions: list[str] = []
    for event in learning_events:
        data = loads(event.event_data or '{}')
        if event.event_type == 'paper_upload':
            recent_actions.append(f"上传《{_clip_text(data.get('filename'), 40)}》")
        elif event.event_type == 'paper_open':
            recent_actions.append('打开文献阅读')
        elif event.event_type == 'paper_read':
            page = data.get('page')
            recent_actions.append(f'阅读至第 {page} 页' if page else '持续阅读')
        elif event.event_type == 'ai_message':
            q = _clip_text(data.get('question') or data.get('content'), 60)
            if q:
                recent_actions.append(f'提问：{q}')

    total = int(total_papers or 0)
    parsed = int(parsed_papers or 0)

    return {
        'hour': now.hour,
        'total_papers': total,
        'parsed_papers': parsed,
        'pending_papers': max(total - parsed, 0),
        'graph_count': int(graph_count or 0),
        'session_count': int(session_count or 0),
        'report_count': int(report_count or 0),
        'today_focus_minutes': int(today_focus or 0),
        'recent_paper_titles': [
            _clip_text(p.title or p.original_filename, 42)
            for p in papers[:3]
            if (p.title or p.original_filename)
        ],
        'recent_graph_names': [_clip_text(g.name, 36) for g in graphs[:2] if g.name],
        'top_keywords': [kw for kw, _ in sorted(keywords.items(), key=lambda x: -x[1])[:4]],
        'recent_questions': [_clip_text(q, 80) for q in recent_questions if q],
        'recent_actions': recent_actions[:5],
    }


def _time_of_day_label(hour: int) -> str:
    if hour < 6:
        return '深夜'
    if hour < 12:
        return '上午'
    if hour < 14:
        return '中午'
    if hour < 18:
        return '下午'
    return '晚上'


def _format_dashboard_brief(context: dict[str, Any]) -> str:
    lines = [
        f'文献库：共 {context["total_papers"]} 篇，就绪 {context["parsed_papers"]} 篇，解析中 {context["pending_papers"]} 篇',
        f'知识图谱 {context["graph_count"]} 个，研究对话 {context["session_count"]} 次，研读报告 {context["report_count"]} 份',
        f'今日专注约 {context["today_focus_minutes"]} 分钟',
    ]
    if context['top_keywords']:
        lines.append(f'近期主题词：{"、".join(context["top_keywords"])}')
    if context['recent_paper_titles']:
        lines.append(f'最近接触的文献：{"；".join(context["recent_paper_titles"])}')
    if context['recent_graph_names']:
        lines.append(f'最近的图谱：{"；".join(context["recent_graph_names"])}')
    if context['recent_questions']:
        lines.append(f'最近问过：{"；".join(context["recent_questions"])}')
    if context['recent_actions']:
        lines.append(f'近期动作：{"；".join(context["recent_actions"])}')
    return '\n'.join(lines)


def _normalize_dashboard_suggestion(text: str) -> str:
    """兜底：强制收敛为一句。"""
    cleaned = ' '.join((text or '').strip().split())
    if not cleaned:
        return cleaned
    for sep in ('。', '！', '？', '.', '!', '?', '\n'):
        idx = cleaned.find(sep)
        if idx != -1:
            cleaned = cleaned[: idx + 1]
            break
    if cleaned[-1] not in '。！？':
        cleaned += '。'
    return cleaned


def _build_dashboard_prompt(context: dict[str, Any]) -> str:
    brief = _format_dashboard_brief(context)
    time_label = _time_of_day_label(context['hour'])

    if context['total_papers'] == 0:
        return f"""用户刚打开工作台，文献库还是空的。当前是{time_label}。

请写【一句话】（35-50字），像朋友在旁轻声提醒，引导 ta 上传第一篇最在意的文献。
要有温度，禁止说教，禁止「你还没有」「0篇」。"""

    return f"""请根据下方素材，为工作台 Banner 写【一句话】温馨提示。

【素材（内化理解，禁止复述清单）】
{brief}
当前时段：{time_label}

【坏示范 - 严禁】
❌ 两句或用分号连接
❌ 「可以继续延展…今天挑 2–3 篇做多文献对比…」
❌ 「今天很适合生成知识图谱…」
❌ 冷冰冰的说明书语气

【好示范 - 学习语感（只一句，有人情味）】
✅ 「SegFormer 那条线先盯住一个点啃透，比再加新论文管用。」
✅ 「解析还在跑，正好把上周卡住的 U-Net 问题翻出来，对着已就绪那篇再追问一轮。」
✅ 「图谱里 RAG 和分割已经分开了，别急，先把最让你别扭的那个节点问清楚。」

【硬性要求】
- 只输出 1 句话，35-55 字，必须以 。！？ 之一结尾
- 只点 1 个此刻最值得做的动作，语气温暖、像熟人搭话
- 最多自然带入 1 个文献/图谱/问题名
- 基于真实素材，禁止编造"""


def get_time_greeting() -> dict[str, str]:
    hour = datetime.now().hour
    if hour < 6:
        return {'text': '夜深了', 'emoji': '🌙'}
    if hour < 12:
        return {'text': '上午好', 'emoji': '☀️'}
    if hour < 14:
        return {'text': '中午好', 'emoji': '🌤️'}
    if hour < 18:
        return {'text': '下午好', 'emoji': '🌤️'}
    return {'text': '晚上好', 'emoji': '🌙'}


def _extract_recent_focus(context: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for kw in context.get('top_keywords', [])[:2]:
        if kw and kw not in tags:
            tags.append(kw)
    for name in context.get('recent_graph_names', [])[:1]:
        label = f'图谱：{name}'
        if label not in tags:
            tags.append(label)
    for title in context.get('recent_paper_titles', [])[:1]:
        if title and title not in tags:
            tags.append(title)
    for q in context.get('recent_questions', [])[:1]:
        if q and q not in tags:
            tags.append(_clip_text(q, 48))
    return tags[:4]


async def generate_dashboard_greeting(db: AsyncSession, user: User) -> dict[str, Any]:
    """实时生成工作台 Banner 文案，不缓存、不落库。"""
    context = await _collect_dashboard_context(db, user.id)
    greeting = get_time_greeting()
    recent_focus = _extract_recent_focus(context)
    prompt = _build_dashboard_prompt(context)
    suggestion = _normalize_dashboard_suggestion(await _generate_summary(prompt, 'dashboard'))
    return {
        'greeting': greeting['text'],
        'emoji': greeting['emoji'],
        'recent_focus': recent_focus,
        'suggestion': suggestion,
        'generated_at': datetime.utcnow().isoformat(),
    }


async def generate_dashboard_insight(db: AsyncSession, user: User) -> dict[str, Any]:
    """兼容旧调用方。"""
    payload = await generate_dashboard_greeting(db, user)
    return {
        'insight': payload['suggestion'],
        'generated_at': payload.get('generated_at'),
    }
