from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.redis import redis_client
from app.models import Paper, ParseTask, User
from app.utils.json_utils import loads

settings = get_settings()


def quota_of(user: User) -> dict:
    q = loads(user.quota_json, {}) if getattr(user, 'quota_json', None) else {}
    return {
        'single_file_max_mb': q.get('single_file_max_mb', settings.default_single_file_max_mb),
        'total_papers': q.get('total_papers', settings.default_total_papers),
        'daily_qa_calls': q.get('daily_qa_calls', settings.default_daily_qa_calls),
        'concurrent_tasks': q.get('concurrent_tasks', settings.default_concurrent_tasks),
        'vector_storage_mb': q.get('vector_storage_mb', 10240),
        'alert_threshold': q.get('alert_threshold', 0.8),
    }


class QuotaService:
    async def _expire_stale_parse_tasks(self, db: AsyncSession, user_id: int) -> None:
        """
        清理异常残留任务。

        解决的问题：
        worker / MySQL / LLM 异常后，parse_tasks 可能长期停在 pending / queued / running，
        之后上传或重解析时会一直提示“当前解析任务已达到单用户并发限制”。

        规则：
        1. pending / queued 超过 30 分钟，自动 failed；
        2. running 超过 60 分钟，自动 failed；
        3. running 但 start_time 为空，也视为异常任务。
        """
        now = datetime.now(BEIJING_TZ)
        queued_deadline = now - timedelta(minutes=30)
        running_deadline = now - timedelta(minutes=60)

        await db.execute(
            update(ParseTask)
            .where(
                ParseTask.user_id == user_id,
                ParseTask.status.in_(['pending', 'queued', 'running']),
                or_(
                    and_(
                        ParseTask.status.in_(['pending', 'queued']),
                        ParseTask.created_at < queued_deadline,
                    ),
                    and_(
                        ParseTask.status == 'running',
                        or_(
                            ParseTask.start_time == None,  # noqa: E711
                            ParseTask.start_time < running_deadline,
                        ),
                    ),
                ),
            )
            .values(
                status='failed',
                end_time=now,
                error_log='auto failed stale parse task before quota check',
            )
        )
        await db.commit()

    async def check_upload(self, db: AsyncSession, user: User, file_size: int) -> None:
        await self._expire_stale_parse_tasks(db, user.id)

        q = quota_of(user)

        max_bytes = int(q['single_file_max_mb']) * 1024 * 1024
        if file_size > max_bytes:
            raise HTTPException(400, f"文件超出单文件上传上限：{q['single_file_max_mb']}MB")

        count = (
            await db.execute(
                select(func.count(Paper.id)).where(
                    Paper.user_id == user.id,
                    Paper.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar() or 0

        if int(count) >= int(q['total_papers']):
            raise HTTPException(403, '已达到文献上传总数配额上限')

        running = (
            await db.execute(
                select(func.count(ParseTask.id)).where(
                    ParseTask.user_id == user.id,
                    ParseTask.status.in_(['pending', 'queued', 'running']),
                )
            )
        ).scalar() or 0

        if int(running) >= int(q['concurrent_tasks']):
            raise HTTPException(429, '当前解析任务已达到单用户并发限制，请稍后再试')

    async def check_daily_qa(self, user: User) -> None:
        q = quota_of(user)
        key = f"quota:qa:{user.id}:{date.today().isoformat()}"
        used = int(await redis_client.get(key) or 0)

        if used >= int(q['daily_qa_calls']):
            raise HTTPException(403, '已达到每日问答调用次数配额')

        await redis_client.incr(key)
        await redis_client.expire(key, 86400 * 2)