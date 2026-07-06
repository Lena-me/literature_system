from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.trace_middleware import get_trace_id
from app.services.system_log_service import format_http_message, log_level_for_http_status, schedule_system_log

logger = logging.getLogger(__name__)


async def _persist(level: str, message: str, request: Request, exc: BaseException | None = None) -> None:
    trace_id = get_trace_id(request)
    # 500 响应优先返回；落库在后台进行，且进程日志已同步写入作为兜底
    schedule_system_log(
        level=level,
        message=message,
        service_name='api',
        trace_id=trace_id,
        exception=exc,
    )


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    await _persist(
        'WARN',
        f'请求校验失败 {request.url.path}: {exc.errors()}'[:8000],
        request,
        exc,
    )
    return JSONResponse(status_code=422, content={'detail': exc.errors()})


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    level = log_level_for_http_status(exc.status_code)
    if level:
        await _persist(
            level,
            format_http_message(exc.status_code, exc.detail, request.url.path),
            request,
            exc if level == 'ERROR' else None,
        )
    return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail})


async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, StarletteHTTPException):
        return await handle_http_exception(request, exc)
    logger.exception('未捕获异常 %s', request.url.path)
    await _persist(
        'ERROR',
        f'未捕获异常 {request.url.path}: {exc}',
        request,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={'detail': str(exc), 'path': request.url.path, 'trace_id': get_trace_id(request)},
    )
