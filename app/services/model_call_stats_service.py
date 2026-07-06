from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select

from app.db.mysql import celery_db
from app.models import ModelCallStat

logger = logging.getLogger(__name__)


def record_llm_call(
    model_id: int,
    *,
    success: bool,
    tokens: int = 0,
    latency_ms: float = 0,
) -> None:
    """记录一次 LLM 调用（同步写入，供 chat/stream 埋点使用）。"""
    if not model_id:
        return

    today = date.today()
    tokens = max(int(tokens or 0), 0)
    latency_ms = max(float(latency_ms or 0), 0.0)

    try:
        with celery_db() as db:
            row = db.execute(
                select(ModelCallStat).where(
                    ModelCallStat.model_id == model_id,
                    ModelCallStat.date == today,
                )
            ).scalar_one_or_none()

            if not row:
                row = ModelCallStat(
                    model_id=model_id,
                    date=today,
                    total_calls=0,
                    success_count=0,
                    total_tokens=0,
                    avg_latency_ms=0,
                    p95_latency_ms=0,
                )
                db.add(row)

            prev_calls = int(row.total_calls or 0)
            row.total_calls = prev_calls + 1
            if success:
                row.success_count = int(row.success_count or 0) + 1
            row.total_tokens = int(row.total_tokens or 0) + tokens

            if latency_ms > 0:
                if prev_calls == 0:
                    row.avg_latency_ms = latency_ms
                    row.p95_latency_ms = latency_ms
                else:
                    row.avg_latency_ms = (
                        float(row.avg_latency_ms or 0) * prev_calls + latency_ms
                    ) / (prev_calls + 1)
                    row.p95_latency_ms = max(float(row.p95_latency_ms or 0), latency_ms)

            db.commit()
    except Exception:
        logger.exception('record_llm_call failed model_id=%s', model_id)
