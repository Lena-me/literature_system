from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select

from app.db.mysql import celery_db
from app.models import Paper, ParseTask
from app.services.pipeline_service import PaperPipelineService
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
        try:
            _mark_failed(paper_id, exc)
        except Exception:
            pass
        raise


def _latest_task(db, paper_id: int) -> ParseTask | None:
    result = db.execute(
        select(ParseTask)
        .where(ParseTask.paper_id == paper_id)
        .order_by(ParseTask.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


def _mark_running(paper_id: int) -> None:
    with celery_db() as db:
        task = _latest_task(db, paper_id)
        paper = db.get(Paper, paper_id)
        if paper:
            paper.parse_status = 'parsing'
        if task:
            task.status = 'running'
            task.start_time = datetime.utcnow()
            task.end_time = None
            task.error_log = None
        db.commit()


def _mark_completed(paper_id: int) -> None:
    with celery_db() as db:
        task = _latest_task(db, paper_id)
        paper = db.get(Paper, paper_id)
        if paper:
            paper.parse_status = 'completed'
        if task:
            task.status = 'completed'
            task.end_time = datetime.utcnow()
        db.commit()


def _mark_failed(paper_id: int, exc: Exception) -> None:
    with celery_db() as db:
        task = _latest_task(db, paper_id)
        paper = db.get(Paper, paper_id)
        if paper:
            paper.parse_status = 'failed'
        if task:
            task.status = 'failed'
            task.end_time = datetime.utcnow()
            task.error_log = f'{type(exc).__name__}: {str(exc)[:3000]}'
        db.commit()
