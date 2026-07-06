from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))

from sqlalchemy import select

from app.db.mysql import celery_db
from app.models import Paper, ParseTask
from app.services.parse_status_events import publish_parse_status
from app.services.pipeline_service import PaperPipelineService
from app.services.system_log_service import new_trace_id, write_system_log_sync
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name='app.workers.tasks.process_paper_pipeline')
def process_paper_pipeline(paper_id: int) -> None:
    """
    Celery 同步任务入口。

    不再使用 asyncio.run() 桥接异步代码。
    改用 celery_db() 同步 session + 同步 pipeline。
    """
    try:
        _mark_running(paper_id)
        PaperPipelineService().parse_extract_vectorize(paper_id)
        _mark_completed(paper_id)
    except Exception as exc:
        trace_id = new_trace_id()
        try:
            _mark_failed(paper_id, exc)
        except Exception:
            pass
        write_system_log_sync(
            level='ERROR',
            message=f'文献解析流水线失败 paper_id={paper_id}: {exc}',
            service_name='celery.paper_pipeline',
            trace_id=trace_id,
            exception=exc,
        )
        raise


def _latest_task(db, paper_id: int) -> ParseTask | None:
    result = db.execute(
        select(ParseTask)
        .where(ParseTask.paper_id == paper_id)
        .order_by(ParseTask.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


def _notify_paper_status(paper: Paper | None, paper_id: int, status: str) -> None:
    if not paper:
        return
    publish_parse_status(
        paper.user_id,
        paper_id,
        status,
        title=paper.title or paper.original_filename,
    )


def _mark_running(paper_id: int) -> None:
    with celery_db() as db:
        task = _latest_task(db, paper_id)
        paper = db.get(Paper, paper_id)
        if paper:
            paper.parse_status = 'parsing'
        if task:
            task.status = 'running'
            task.start_time = datetime.now(BEIJING_TZ)
            task.end_time = None
            task.error_log = None
        db.commit()
        _notify_paper_status(paper, paper_id, 'parsing')


def _mark_completed(paper_id: int) -> None:
    with celery_db() as db:
        task = _latest_task(db, paper_id)
        paper = db.get(Paper, paper_id)
        if paper:
            paper.parse_status = 'completed'
        if task:
            task.status = 'completed'
            task.end_time = datetime.now(BEIJING_TZ)
        db.commit()
        _notify_paper_status(paper, paper_id, 'completed')


def _mark_failed(paper_id: int, exc: Exception) -> None:
    with celery_db() as db:
        task = _latest_task(db, paper_id)
        paper = db.get(Paper, paper_id)
        if paper:
            paper.parse_status = 'failed'
        if task:
            task.status = 'failed'
            task.end_time = datetime.now(BEIJING_TZ)
            task.error_log = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
        db.commit()
        _notify_paper_status(paper, paper_id, 'failed')
