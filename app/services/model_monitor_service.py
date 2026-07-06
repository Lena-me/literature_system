from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModelCallStat, ModelConfig
from app.services.admin_overview_service import P95_LATENCY_HEALTHY_MS, P95_LATENCY_WARN_MS
from app.services.model_scenarios import scenario_name

TREND_DAYS = 7


def _empty_day_stat() -> dict:
    return {
        'calls': 0,
        'success_count': 0,
        'tokens': 0,
        'success_rate': 100.0,
        'avg_latency_ms': 0.0,
        'p95_latency_ms': 0.0,
    }


def _stat_row_to_dict(row: ModelCallStat | None) -> dict:
    if not row:
        return _empty_day_stat()
    calls = int(row.total_calls or 0)
    success = int(row.success_count or 0)
    return {
        'calls': calls,
        'success_count': success,
        'tokens': int(row.total_tokens or 0),
        'success_rate': round(success / calls * 100, 1) if calls else 100.0,
        'avg_latency_ms': round(float(row.avg_latency_ms or 0), 1),
        'p95_latency_ms': round(float(row.p95_latency_ms or 0), 1),
    }


def _p95_meta(avg_p95: float) -> tuple[str, str]:
    if avg_p95 <= 0:
        return 'healthy', '暂无延迟数据'
    if avg_p95 <= P95_LATENCY_HEALTHY_MS:
        return 'healthy', '延迟正常'
    if avg_p95 <= P95_LATENCY_WARN_MS:
        return 'warning', '延迟偏高'
    return 'critical', '延迟过高'


def _build_summary(total_calls: int, success_count: int, total_tokens: int, p95_values: list[float]) -> dict:
    success_rate = round(success_count / total_calls * 100, 1) if total_calls else 100.0
    avg_p95 = round(sum(p95_values) / len(p95_values), 1) if p95_values else 0.0
    p95_health, p95_label = _p95_meta(avg_p95)
    return {
        'total_calls': total_calls,
        'total_tokens': total_tokens,
        'success_rate': success_rate,
        'success_count': success_count,
        'p95_latency_ms': avg_p95,
        'p95_health': p95_health,
        'p95_label': p95_label,
    }


async def _load_stats_in_range(
    db: AsyncSession,
    *,
    start: date,
    end: date,
    model_id: int | None = None,
) -> list[ModelCallStat]:
    stmt = select(ModelCallStat).where(ModelCallStat.date >= start, ModelCallStat.date <= end)
    if model_id is not None:
        stmt = stmt.where(ModelCallStat.model_id == model_id)
    stmt = stmt.order_by(ModelCallStat.date.asc(), ModelCallStat.model_id.asc())
    return (await db.execute(stmt)).scalars().all()


def _trend_series(start: date, end: date, by_date: dict[date, ModelCallStat]) -> list[dict]:
    items: list[dict] = []
    cursor = start
    while cursor <= end:
        row = by_date.get(cursor)
        stat = _stat_row_to_dict(row)
        items.append(
            {
                'date': cursor.isoformat(),
                'calls': stat['calls'],
                'tokens': stat['tokens'],
                'success_rate': stat['success_rate'],
            }
        )
        cursor += timedelta(days=1)
    return items


async def build_models_monitor(db: AsyncSession) -> dict:
    today = date.today()
    start = today - timedelta(days=TREND_DAYS - 1)

    configs = (
        await db.execute(select(ModelConfig).order_by(ModelConfig.model_type.asc(), ModelConfig.id.asc()))
    ).scalars().all()
    stat_rows = await _load_stats_in_range(db, start=start, end=today)

    today_rows = [r for r in stat_rows if r.date == today]
    total_calls = sum(int(r.total_calls or 0) for r in today_rows)
    success_count = sum(int(r.success_count or 0) for r in today_rows)
    total_tokens = sum(int(r.total_tokens or 0) for r in today_rows)
    p95_values = [float(r.p95_latency_ms or 0) for r in today_rows if r.p95_latency_ms]

    stats_by_model_date: dict[tuple[int, date], ModelCallStat] = {
        (r.model_id, r.date): r for r in stat_rows
    }

    items: list[dict] = []
    for cfg in configs:
        today_stat = stats_by_model_date.get((cfg.id, today))
        trend_map = {
            d: stats_by_model_date[(cfg.id, d)]
            for d in (start + timedelta(days=i) for i in range(TREND_DAYS))
            if (cfg.id, d) in stats_by_model_date
        }
        items.append(
            {
                'model_id': cfg.id,
                'model_type': cfg.model_type,
                'scenario': cfg.scenario,
                'scenario_name': scenario_name(cfg.scenario),
                'is_primary': bool(cfg.is_primary),
                'model_name': cfg.model_name,
                'is_active': cfg.is_active,
                'today': _stat_row_to_dict(today_stat),
                'last_7_days': _trend_series(start, today, trend_map),
            }
        )

    summary = _build_summary(total_calls, success_count, total_tokens, p95_values)
    return {
        'date': today.isoformat(),
        'summary': summary,
        'items': items,
        'model_count': len(configs),
        **summary,
    }


async def build_model_detail(db: AsyncSession, model_id: int) -> dict | None:
    cfg = await db.get(ModelConfig, model_id)
    if not cfg:
        return None

    today = date.today()
    start = today - timedelta(days=TREND_DAYS - 1)
    stat_rows = await _load_stats_in_range(db, start=start, end=today, model_id=model_id)
    by_date = {r.date: r for r in stat_rows}
    today_stat = by_date.get(today)

    total_calls = sum(int(r.total_calls or 0) for r in stat_rows)
    success_count = sum(int(r.success_count or 0) for r in stat_rows)
    total_tokens = sum(int(r.total_tokens or 0) for r in stat_rows)
    p95_values = [float(r.p95_latency_ms or 0) for r in stat_rows if r.p95_latency_ms]

    return {
        'model_id': cfg.id,
        'model_type': cfg.model_type,
        'scenario': cfg.scenario,
        'scenario_name': scenario_name(cfg.scenario),
        'is_primary': bool(cfg.is_primary),
        'model_name': cfg.model_name,
        'version': cfg.version,
        'api_endpoint': cfg.api_endpoint,
        'is_active': cfg.is_active,
        'created_at': cfg.created_at.isoformat() if cfg.created_at else None,
        'updated_at': cfg.updated_at.isoformat() if cfg.updated_at else None,
        'today': _stat_row_to_dict(today_stat),
        'period_7d': _build_summary(total_calls, success_count, total_tokens, p95_values),
        'last_7_days': _trend_series(start, today, by_date),
    }


async def attach_today_stats(db: AsyncSession, items: list[dict]) -> None:
    if not items:
        return
    today = date.today()
    ids = [int(x['id']) for x in items]
    rows = (
        await db.execute(
            select(ModelCallStat).where(
                ModelCallStat.model_id.in_(ids),
                ModelCallStat.date == today,
            )
        )
    ).scalars().all()
    stat_map = {r.model_id: r for r in rows}
    for item in items:
        item['today_stats'] = _stat_row_to_dict(stat_map.get(item['id']))
