from __future__ import annotations

import logging
import traceback
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mysql import AsyncSessionLocal, celery_db
from app.models import SystemLog

logger = logging.getLogger(__name__)

_MAX_MESSAGE = 8000
_MAX_STACK = 16000


def new_trace_id() -> str:
    return uuid.uuid4().hex


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return f'{text[: limit - 1]}…'


def _format_exception(exception: BaseException | None, stack_trace: str | None) -> tuple[str | None, str | None]:
    if exception is None:
        return None, _clip(stack_trace, _MAX_STACK)
    exc_type = type(exception).__name__
    st = stack_trace or ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    return exc_type, _clip(st, _MAX_STACK)


def _normalize_level(level: str) -> str:
    upper = (level or 'INFO').upper()
    if upper in {'DEBUG', 'INFO', 'WARN', 'WARNING', 'ERROR', 'CRITICAL'}:
        return 'WARN' if upper == 'WARNING' else upper
    return 'INFO'


def _build_row(
    *,
    level: str,
    message: str,
    service_name: str,
    trace_id: str | None,
    exception: BaseException | None,
    stack_trace: str | None,
    exception_type: str | None,
) -> SystemLog:
    exc_type, st = _format_exception(exception, stack_trace)
    if exception_type:
        exc_type = exception_type
    return SystemLog(
        level=_normalize_level(level),
        service_name=(service_name or 'api')[:100],
        message=_clip(message, _MAX_MESSAGE) or '',
        stack_trace=st,
        trace_id=(trace_id or None),
        exception_type=(exc_type[:200] if exc_type else None),
    )


async def _persist_system_log_row(row: SystemLog) -> None:
    try:
        async with AsyncSessionLocal() as session:
            session.add(row)
            await session.commit()
    except Exception:
        logger.exception('system_logs 落库失败（进程日志已保留）: %s', row.message[:200])


async def write_system_log(
    *,
    level: str,
    message: str,
    service_name: str = 'api',
    trace_id: str | None = None,
    exception: BaseException | None = None,
    stack_trace: str | None = None,
    exception_type: str | None = None,
    db: AsyncSession | None = None,
) -> None:
    """
    写入 system_logs。

    策略：先写进程日志（兜底，不依赖 DB），再尝试独立 session 落库。
    绝大多数 500 是业务代码/外部服务异常，MySQL 连接池仍然可用；
    仅当 MySQL 本身不可达时落库会失败，但 stderr/uvicorn 日志仍保留记录。
    """
    normalized = _normalize_level(level)
    exc_type, st = _format_exception(exception, stack_trace)
    _log_to_process(
        level=normalized,
        message=message,
        service_name=service_name,
        trace_id=trace_id,
        exception_type=exc_type,
        stack_trace=st,
    )

    row = _build_row(
        level=normalized,
        message=message,
        service_name=service_name,
        trace_id=trace_id,
        exception=exception,
        stack_trace=stack_trace,
        exception_type=exception_type,
    )
    if db is not None:
        db.add(row)
        return
    await _persist_system_log_row(row)


def write_system_log_sync(
    *,
    level: str,
    message: str,
    service_name: str = 'worker',
    trace_id: str | None = None,
    exception: BaseException | None = None,
    stack_trace: str | None = None,
    exception_type: str | None = None,
) -> None:
    """Celery / 同步上下文写入 system_logs。"""
    normalized = _normalize_level(level)
    exc_type, st = _format_exception(exception, stack_trace)
    _log_to_process(
        level=normalized,
        message=message,
        service_name=service_name,
        trace_id=trace_id,
        exception_type=exc_type,
        stack_trace=st,
    )

    row = _build_row(
        level=normalized,
        message=message,
        service_name=service_name,
        trace_id=trace_id,
        exception=exception,
        stack_trace=stack_trace,
        exception_type=exception_type,
    )
    try:
        with celery_db() as session:
            session.add(row)
            session.commit()
    except Exception:
        logger.exception('system_logs 落库失败（进程日志已保留）: %s', message[:200])


def _log_to_process(
    *,
    level: str,
    message: str,
    service_name: str,
    trace_id: str | None,
    exception_type: str | None,
    stack_trace: str | None,
) -> None:
    """不依赖数据库的兜底日志，写入 uvicorn/docker 标准输出。"""
    prefix = f'[{service_name}]'
    if trace_id:
        prefix = f'{prefix}[trace={trace_id}]'
    if exception_type:
        prefix = f'{prefix}[{exception_type}]'
    text = f'{prefix} {message}'
    if level in {'ERROR', 'CRITICAL'}:
        if stack_trace:
            logger.error('%s\n%s', text, stack_trace)
        else:
            logger.error(text)
    elif level == 'WARN':
        logger.warning(text)
    else:
        logger.info(text)


def schedule_system_log(
    *,
    level: str,
    message: str,
    service_name: str = 'api',
    trace_id: str | None = None,
    exception: BaseException | None = None,
    stack_trace: str | None = None,
    exception_type: str | None = None,
) -> None:
    """先同步写进程日志（兜底），再后台落库，不阻塞 HTTP 响应。"""
    import asyncio

    normalized = _normalize_level(level)
    exc_type, st = _format_exception(exception, stack_trace)
    _log_to_process(
        level=normalized,
        message=message,
        service_name=service_name,
        trace_id=trace_id,
        exception_type=exc_type,
        stack_trace=st,
    )
    row = _build_row(
        level=normalized,
        message=message,
        service_name=service_name,
        trace_id=trace_id,
        exception=exception,
        stack_trace=stack_trace,
        exception_type=exception_type,
    )

    async def _run() -> None:
        await _persist_system_log_row(row)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())


def log_level_for_http_status(status_code: int) -> str | None:
    if status_code >= 500:
        return 'ERROR'
    if status_code in {429, 408}:
        return 'WARN'
    return None


def format_http_message(status_code: int, detail: Any, path: str) -> str:
    text = detail if isinstance(detail, str) else str(detail)
    return f'HTTP {status_code} {path}: {text}'[:_MAX_MESSAGE]
