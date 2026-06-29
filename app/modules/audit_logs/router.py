from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import require_admin
from app.db.mysql import get_db
from app.models import AuditLog, User
router = APIRouter(prefix='/audit-logs', tags=['行为审计'])

@router.get('')
async def list_logs(module: str | None = None, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    stmt = select(AuditLog)
    if module: stmt = stmt.where(AuditLog.module == module)
    rows = (await db.execute(stmt.order_by(AuditLog.created_at.desc()).limit(500))).scalars().all()
    return [{'id': x.id, 'user_id': x.user_id, 'module': x.module, 'operation_type': x.operation_type, 'operation_result': x.operation_result, 'ip_address': x.ip_address, 'risk_flag': x.risk_flag, 'created_at': x.created_at} for x in rows]
