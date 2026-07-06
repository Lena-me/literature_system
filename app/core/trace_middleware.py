from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services.system_log_service import new_trace_id


class TraceMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 trace_id，便于异常日志关联。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get('x-trace-id') or request.headers.get('X-Trace-Id') or new_trace_id()
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers['X-Trace-Id'] = trace_id
        return response


def get_trace_id(request: Request) -> str | None:
    return getattr(request.state, 'trace_id', None)
