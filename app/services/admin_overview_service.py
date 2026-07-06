from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.milvus.client import MilvusChunkStore
from app.models import ModelCallStat, Paper, ParseTask, QAMessage, QASession, SystemLog, User
from app.services.system_pause import is_system_paused

# 无 per-user Token 表时，用 QA 次数估算 Token（单次约 800）
QA_TOKEN_ESTIMATE = 800
# 单次文献上传估算 Token（解析+向量化）
UPLOAD_TOKEN_ESTIMATE = 2000

PARSE_WEIGHT = 0.4
MODEL_WEIGHT = 0.4
INFRA_WEIGHT = 0.2

P95_LATENCY_HEALTHY_MS = 3000
P95_LATENCY_WARN_MS = 8000


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _health_status(total_score: float) -> str:
    if total_score >= 90:
        return 'healthy'
    if total_score >= 75:
        return 'warning'
    return 'critical'


def _cluster_label(exception_type: str | None, message: str | None) -> str:
    if exception_type and exception_type.strip():
        return exception_type.strip()[:120]
    msg = (message or '').strip()
    if not msg:
        return 'UnknownError'
    return msg[:80] + ('…' if len(msg) > 80 else '')


async def _composite_health(db: AsyncSession, since: datetime) -> dict:
    # --- 解析健康度 (40%) ---
    parse_row = (
        await db.execute(
            select(
                func.count().label('total'),
                func.sum(case((ParseTask.status == 'completed', 1), else_=0)).label('success'),
            ).where(ParseTask.created_at >= since)
        )
    ).one()
    parse_total = int(parse_row.total or 0)
    parse_success = int(parse_row.success or 0)
    parse_score = 100.0 if parse_total == 0 else round(parse_success / parse_total * 100, 1)

    # --- 模型健康度 (40%)：今日加权成功率 ---
    today = date.today()
    model_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(ModelCallStat.total_calls), 0),
                func.coalesce(func.sum(ModelCallStat.success_count), 0),
            ).where(ModelCallStat.date == today)
        )
    ).one()
    model_total = int(model_row[0] or 0)
    model_success = int(model_row[1] or 0)
    if model_total == 0:
        qa_today = (
            await db.execute(
                select(func.count())
                .select_from(QAMessage)
                .where(QAMessage.role == 'user', func.date(QAMessage.created_at) == today)
            )
        ).scalar_one()
        model_total = int(qa_today or 0)
        model_success = model_total
    model_score = 100.0 if model_total == 0 else round(model_success / model_total * 100, 1)

    # --- 基建与日志健康度 (20%) ---
    log_row = (
        await db.execute(
            select(
                func.count().label('total'),
                func.sum(case((SystemLog.level == 'ERROR', 1), else_=0)).label('errors'),
            ).where(SystemLog.logged_at >= since)
        )
    ).one()
    log_total = int(log_row.total or 0)
    log_errors = int(log_row.errors or 0)
    error_ratio = (log_errors / log_total) if log_total > 0 else 0.0
    if log_total == 0 or error_ratio < 0.01:
        infra_score = 100.0
        infra_reason = 'ERROR 占比 < 1%，不扣分'
    elif error_ratio <= 0.05:
        infra_score = 80.0
        infra_reason = f'ERROR 占比 {error_ratio * 100:.1f}%，扣分至 80'
    else:
        infra_score = 50.0
        infra_reason = f'ERROR 占比 {error_ratio * 100:.1f}%，扣分至 50'

    total_score = round(
        parse_score * PARSE_WEIGHT + model_score * MODEL_WEIGHT + infra_score * INFRA_WEIGHT,
        1,
    )
    status = _health_status(total_score)
    paused = await is_system_paused()

    deductions = {
        'parse': round((100 - parse_score) * PARSE_WEIGHT, 1),
        'model': round((100 - model_score) * MODEL_WEIGHT, 1),
        'infra': round((100 - infra_score) * INFRA_WEIGHT, 1),
    }

    return {
        'total_score': total_score,
        'status': status,
        'paused': paused,
        'components': {
            'parse': {
                'score': parse_score,
                'weight': PARSE_WEIGHT,
                'total_tasks': parse_total,
                'success_tasks': parse_success,
                'detail': f'近24h 解析成功率 {parse_score}%' if parse_total else '近24h 无解析任务，默认满分',
            },
            'model': {
                'score': model_score,
                'weight': MODEL_WEIGHT,
                'total_calls': model_total,
                'success_calls': model_success,
                'detail': f'今日模型加权成功率 {model_score}%' if model_total else '今日无模型调用，默认满分',
            },
            'infra': {
                'score': infra_score,
                'weight': INFRA_WEIGHT,
                'log_total': log_total,
                'error_count': log_errors,
                'error_ratio': round(error_ratio, 4),
                'detail': infra_reason if log_total else '近24h 无系统日志，默认满分',
            },
        },
        'deductions': deductions,
    }


def _cluster_from_rows(rows: list[tuple], limit: int) -> list[dict]:
    buckets: dict[str, int] = {}
    for (summary, count) in rows:
        key = (summary or 'UnknownError')[:120]
        buckets[key] = buckets.get(key, 0) + int(count)
    return [
        {'summary': k, 'count': v}
        for k, v in sorted(buckets.items(), key=lambda x: x[1], reverse=True)[:limit]
    ]


async def _cluster_system_logs(
    db: AsyncSession,
    since: datetime | None,
    levels: tuple[str, ...],
    limit: int = 10,
) -> list[dict]:
    cluster_key = func.coalesce(
        SystemLog.exception_type,
        func.substring(SystemLog.message, 1, 80),
    )
    stmt = select(cluster_key.label('summary'), func.count().label('count')).where(
        SystemLog.level.in_(levels)
    )
    if since is not None:
        stmt = stmt.where(SystemLog.logged_at >= since)
    rows = (
        await db.execute(
            stmt.group_by(cluster_key).order_by(func.count().desc()).limit(limit)
        )
    ).all()
    return _cluster_from_rows([(r.summary, r.count) for r in rows], limit)


async def _cluster_failed_tasks(
    db: AsyncSession,
    since: datetime | None,
    limit: int = 10,
) -> list[dict]:
    stmt = select(ParseTask.error_log).where(ParseTask.status == 'failed')
    if since is not None:
        stmt = stmt.where(ParseTask.created_at >= since)
    task_rows = (await db.execute(stmt.order_by(ParseTask.created_at.desc()).limit(500))).all()
    buckets: dict[str, int] = {}
    for (err,) in task_rows:
        key = _cluster_label(None, err)
        buckets[key] = buckets.get(key, 0) + 1
    return [
        {'summary': k, 'count': v}
        for k, v in sorted(buckets.items(), key=lambda x: x[1], reverse=True)[:limit]
    ]


async def _error_clusters(db: AsyncSession, since: datetime, limit: int = 10) -> dict:
    since_7d = datetime.now() - timedelta(days=7)

    # 1) 近 24h ERROR 系统日志
    clusters = await _cluster_system_logs(db, since, ('ERROR', 'CRITICAL'), limit)
    if clusters:
        return {'items': clusters, 'source': 'system_logs_24h'}

    # 2) 近 7 天 ERROR/WARN 系统日志
    clusters = await _cluster_system_logs(db, since_7d, ('ERROR', 'CRITICAL', 'WARN'), limit)
    if clusters:
        return {'items': clusters, 'source': 'system_logs_7d'}

    # 3) 近 24h 失败解析任务
    clusters = await _cluster_failed_tasks(db, since, limit)
    if clusters:
        return {'items': clusters, 'source': 'parse_tasks_24h'}

    # 4) 全量失败解析任务（与重构前 fallback 一致）
    clusters = await _cluster_failed_tasks(db, None, limit)
    if clusters:
        return {'items': clusters, 'source': 'parse_tasks_all'}

    return {'items': [], 'source': 'none'}


async def _llm_today_weighted(db: AsyncSession) -> dict:
    today = date.today()
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(ModelCallStat.total_calls), 0),
                func.coalesce(func.sum(ModelCallStat.success_count), 0),
                func.coalesce(func.sum(ModelCallStat.total_tokens), 0),
            ).where(ModelCallStat.date == today)
        )
    ).one()
    total, success, tokens = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
    if total == 0:
        qa_today = (
            await db.execute(
                select(func.count())
                .select_from(QAMessage)
                .where(QAMessage.role == 'user', func.date(QAMessage.created_at) == today)
            )
        ).scalar_one()
        total = int(qa_today or 0)
        success = total
        tokens = total * QA_TOKEN_ESTIMATE
    rate = round(success / total, 4) if total else 1.0
    return {
        'total': total,
        'success_count': success,
        'success_rate': rate,
        'total_tokens': tokens,
    }


async def _daily_series(db: AsyncSession, days: int = 7) -> dict:
    today = date.today()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days - 1, -1, -1)]
    date_set = set(dates)

    upload_result = (
        await db.execute(
            select(func.date(Paper.upload_time).label('d'), func.count().label('cnt'))
            .select_from(Paper)
            .where(func.date(Paper.upload_time).in_(date_set))
            .group_by(func.date(Paper.upload_time))
        )
    ).all()
    upload_map = {str(r.d): int(r.cnt) for r in upload_result}

    parse_result = (
        await db.execute(
            select(func.date(ParseTask.end_time).label('d'), func.count().label('cnt'))
            .select_from(ParseTask)
            .where(func.date(ParseTask.end_time).in_(date_set), ParseTask.status == 'completed')
            .group_by(func.date(ParseTask.end_time))
        )
    ).all()
    parse_map = {str(r.d): int(r.cnt) for r in parse_result}

    qa_result = (
        await db.execute(
            select(func.date(QAMessage.created_at).label('d'), func.count().label('cnt'))
            .select_from(QAMessage)
            .where(func.date(QAMessage.created_at).in_(date_set), QAMessage.role == 'user')
            .group_by(func.date(QAMessage.created_at))
        )
    ).all()
    qa_map = {str(r.d): int(r.cnt) for r in qa_result}

    queued_result = (
        await db.execute(
            select(func.date(ParseTask.created_at).label('d'), func.count().label('cnt'))
            .select_from(ParseTask)
            .where(
                func.date(ParseTask.created_at).in_(date_set),
                ParseTask.status.in_(['queued', 'running']),
            )
            .group_by(func.date(ParseTask.created_at))
        )
    ).all()
    queued_map = {str(r.d): int(r.cnt) for r in queued_result}

    return {
        'dates': dates,
        'upload': [upload_map.get(d, 0) for d in dates],
        'parse': [parse_map.get(d, 0) for d in dates],
        'qa': [qa_map.get(d, 0) for d in dates],
        'queued_tasks': [queued_map.get(d, 0) for d in dates],
    }


async def _vector_total() -> int:
    try:
        return int(MilvusChunkStore().stats().get('total_vectors', 0))
    except Exception:
        return 0


async def _queued_tasks_count(db: AsyncSession) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(ParseTask)
                .where(ParseTask.status.in_(['queued', 'running']))
            )
        ).scalar_one()
        or 0
    )


async def _aggregate_user_scores(
    db: AsyncSession,
    start: date | None = None,
    end: date | None = None,
) -> dict[int, dict]:
    upload_stmt = select(Paper.user_id, func.count().label('cnt')).group_by(Paper.user_id)
    if start is not None:
        upload_stmt = upload_stmt.where(func.date(Paper.upload_time) >= start)
    if end is not None:
        upload_stmt = upload_stmt.where(func.date(Paper.upload_time) <= end)
    upload_rows = (await db.execute(upload_stmt)).all()
    upload_map = {int(r.user_id): int(r.cnt) for r in upload_rows}

    qa_stmt = (
        select(QASession.user_id, func.count().label('cnt'))
        .join(QAMessage, QAMessage.session_id == QASession.id)
        .where(QAMessage.role == 'user')
        .group_by(QASession.user_id)
    )
    if start is not None:
        qa_stmt = qa_stmt.where(func.date(QAMessage.created_at) >= start)
    if end is not None:
        qa_stmt = qa_stmt.where(func.date(QAMessage.created_at) <= end)
    qa_rows = (await db.execute(qa_stmt)).all()
    qa_map = {int(r.user_id): int(r.cnt) for r in qa_rows}

    scores: dict[int, dict] = {}
    for uid in set(upload_map) | set(qa_map):
        uploads = upload_map.get(uid, 0)
        qa_calls = qa_map.get(uid, 0)
        tokens = qa_calls * QA_TOKEN_ESTIMATE + uploads * UPLOAD_TOKEN_ESTIMATE
        scores[uid] = {
            'uploads': uploads,
            'qa_calls': qa_calls,
            'tokens': tokens,
            'consumption': tokens,
        }
    return scores


async def _top_users_from_scores(
    db: AsyncSession,
    scores: dict[int, dict],
    limit: int,
) -> list[dict]:
    if not scores:
        return []
    top_ids = sorted(scores.keys(), key=lambda u: scores[u]['consumption'], reverse=True)[:limit]
    users = (await db.execute(select(User).where(User.id.in_(top_ids), User.role != 'admin'))).scalars().all()
    user_map = {u.id: u for u in users}
    max_consumption = max(scores[uid]['consumption'] for uid in top_ids) or 1
    result = []
    for uid in top_ids:
        u = user_map.get(uid)
        if not u:
            continue
        b = scores[uid]
        result.append(
            {
                'id': uid,
                'username': u.username,
                'name': u.name,
                'tokens': b['tokens'],
                'uploads': b['uploads'],
                'qa_calls': b['qa_calls'],
                'consumption': b['consumption'],
                'consumption_pct': round(b['consumption'] / max_consumption * 100, 1),
            }
        )
    return result


async def _top_users_lifetime(db: AsyncSession, limit: int = 3) -> list[dict]:
    """无近期活跃时，用累计上传数 + 全量 QA 估算消耗。"""
    users = (
        await db.execute(
            select(User)
            .where(User.role != 'admin')
            .order_by(User.paper_upload_count.desc())
            .limit(limit * 3)
        )
    ).scalars().all()
    if not users:
        return []
    user_ids = [u.id for u in users]
    qa_rows = (
        await db.execute(
            select(QASession.user_id, func.count().label('cnt'))
            .join(QAMessage, QAMessage.session_id == QASession.id)
            .where(QAMessage.role == 'user', QASession.user_id.in_(user_ids))
            .group_by(QASession.user_id)
        )
    ).all()
    qa_map = {int(r.user_id): int(r.cnt) for r in qa_rows}
    scored = []
    for u in users:
        uploads = int(u.paper_upload_count or 0)
        qa_calls = qa_map.get(u.id, 0)
        tokens = qa_calls * QA_TOKEN_ESTIMATE + uploads * UPLOAD_TOKEN_ESTIMATE
        scored.append((u, uploads, qa_calls, tokens))
    scored.sort(key=lambda x: x[3], reverse=True)
    top = scored[:limit]
    max_consumption = top[0][3] if top else 1
    return [
        {
            'id': u.id,
            'username': u.username,
            'name': u.name,
            'tokens': tokens,
            'uploads': uploads,
            'qa_calls': qa_calls,
            'consumption': tokens,
            'consumption_pct': round(tokens / max_consumption * 100, 1),
        }
        for u, uploads, qa_calls, tokens in top
    ]


async def _top_users(db: AsyncSession, limit: int = 3) -> dict:
    today = date.today()
    start_7d = today - timedelta(days=6)

    scores = await _aggregate_user_scores(db, start=today, end=today)
    if scores:
        return {'items': await _top_users_from_scores(db, scores, limit), 'period': 'today'}

    scores = await _aggregate_user_scores(db, start=start_7d, end=today)
    if scores:
        return {'items': await _top_users_from_scores(db, scores, limit), 'period': '7d'}

    items = await _top_users_lifetime(db, limit)
    return {'items': items, 'period': 'lifetime' if items else 'none'}


async def build_overview(db: AsyncSession) -> dict:
    since = datetime.now() - timedelta(hours=24)
    health = await _composite_health(db, since)
    llm = await _llm_today_weighted(db)
    series = await _daily_series(db)
    vector_total = await _vector_total()
    queued = await _queued_tasks_count(db)
    error_clusters = await _error_clusters(db, since)
    top_users = await _top_users(db)

    return {
        'health': health,
        'cards': {
            'llm_today': {**llm, 'sparkline': series['qa'][-7:]},
            'vector_total': vector_total,
            'queued_tasks': queued,
            'sparklines': {
                'llm': series['qa'][-7:],
                'vector': series['parse'][-7:],
                'tasks': series['queued_tasks'],
            },
        },
        'trends': {
            'dates': series['dates'],
            'upload': series['upload'],
            'parse': series['parse'],
            'qa': series['qa'],
        },
        'error_clusters': error_clusters.get('items', []),
        'error_clusters_meta': {'source': error_clusters.get('source', 'none')},
        'top_users': top_users.get('items', []),
        'top_users_meta': {'period': top_users.get('period', 'none')},
    }


async def build_models_monitor(db: AsyncSession) -> dict:
    from app.services.model_monitor_service import build_models_monitor as _build

    return await _build(db)
