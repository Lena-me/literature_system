from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import require_admin
from app.db.mysql import get_db
from app.models import AuditLog, User
from app.schemas.admin import AdminAuditLogOut
from app.services.admin_logs_service import audit_operation_summary

router = APIRouter(prefix='/audit-logs', tags=['行为审计'])

@router.get('', response_model=list[AdminAuditLogOut])
async def list_logs(module: str | None = None, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    stmt = select(AuditLog, User.username).outerjoin(User, AuditLog.user_id == User.id)
    if module:
        stmt = stmt.where(AuditLog.module == module)
    rows = (await db.execute(stmt.order_by(AuditLog.created_at.desc()).limit(500))).all()
    return [
        AdminAuditLogOut(
            username=username,
            module=x.module,
            operation_type=x.operation_type,
            operation_summary=audit_operation_summary(x.module, x.operation_type, content_raw=x.operation_content),
            operation_result=x.operation_result,
            ip_address=x.ip_address,
            risk_flag=x.risk_flag,
            created_at=x.created_at,
        ).model_dump()
        for x, username in rows
    ]
