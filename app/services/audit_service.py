from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mysql import AsyncSessionLocal
from app.models import AuditLog
from app.utils.json_utils import dumps


def client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def audit_content(data: dict[str, Any] | str) -> str:
    if isinstance(data, str):
        return data
    return dumps(data)


async def write_audit(
    db: AsyncSession,
    user_id: int | None,
    module: str,
    operation_type: str,
    content: str,
    result: str = 'success',
    ip: str | None = None,
    risk_flag: int = 0,
    risk: int | None = None,
) -> None:
    if risk is not None:
        risk_flag = risk
    db.add(
        AuditLog(
            user_id=user_id,
            module=module,
            operation_type=operation_type,
            operation_content=content,
            operation_result=result,
            ip_address=ip,
            risk_flag=risk_flag,
        )
    )


async def audit_action(
    db: AsyncSession,
    *,
    user_id: int | None,
    module: str,
    operation_type: str,
    content: dict[str, Any] | str,
    request: Request | None = None,
    ip: str | None = None,
    result: str = 'success',
    risk: int = 0,
) -> None:
    await write_audit(
        db,
        user_id,
        module,
        operation_type,
        audit_content(content),
        result=result,
        ip=ip if ip is not None else client_ip(request),
        risk=risk,
    )


async def audit_action_standalone(
    *,
    user_id: int | None,
    module: str,
    operation_type: str,
    content: dict[str, Any] | str,
    request: Request | None = None,
    ip: str | None = None,
    result: str = 'success',
    risk: int = 0,
) -> None:
    """独立事务写入审计，适用于登录失败等不与其他业务共用的场景。"""
    try:
        async with AsyncSessionLocal() as db:
            await audit_action(
                db,
                user_id=user_id,
                module=module,
                operation_type=operation_type,
                content=content,
                request=request,
                ip=ip,
                result=result,
                risk=risk,
            )
            await db.commit()
    except Exception:
        pass
