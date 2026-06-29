from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AuditLog

async def write_audit(db: AsyncSession, user_id: int | None, module: str, operation_type: str, content: str, result: str = 'success', ip: str | None = None, risk_flag: int = 0, risk: int | None = None) -> None:
    if risk is not None:
        risk_flag = risk
    db.add(AuditLog(user_id=user_id, module=module, operation_type=operation_type, operation_content=content, operation_result=result, ip_address=ip, risk_flag=risk_flag))
