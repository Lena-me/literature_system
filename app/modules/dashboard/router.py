from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import User
from app.services.activity_report_service import generate_dashboard_greeting

router = APIRouter(prefix='/dashboard', tags=['工作台'])


@router.get('/greeting')
async def get_dashboard_greeting(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """工作台 Banner：快速聚合近期状态 + 异步 LLM 一句话建议（不缓存）。"""
    return await generate_dashboard_greeting(db, user)
