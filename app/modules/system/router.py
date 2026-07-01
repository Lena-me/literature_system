from fastapi import APIRouter
from app.db.redis import redis_client
router = APIRouter(prefix='/system', tags=['系统'])

@router.get('/health')
async def health():
    
    try:
        redis_ok = await redis_client.ping()
    except Exception as exc:
        return {'status':'degraded', 'redis': False, 'error': str(exc)}
    return {'status':'ok', 'redis': redis_ok}

from fastapi import Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import require_admin
from app.db.mysql import get_db
from app.integrations.milvus.client import MilvusChunkStore
from app.models import Paper, QAMessage, Report, KnowledgeGraph, User

@router.get('/operation-stats')
async def operation_stats(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    total_uploaded = (await db.execute(select(func.count()).select_from(Paper))).scalar_one()
    total_parsed = (await db.execute(select(func.count()).select_from(Paper).where(Paper.parse_status.in_(['completed','indexed'])))).scalar_one()
    total_qa_calls = (await db.execute(select(func.count()).select_from(QAMessage).where(QAMessage.role == 'user'))).scalar_one()
    total_reports = (await db.execute(select(func.count()).select_from(Report))).scalar_one()
    total_graphs = (await db.execute(select(func.count()).select_from(KnowledgeGraph))).scalar_one()
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    active_users = (await db.execute(select(func.count()).select_from(User).where(User.last_login_at.is_not(None)))).scalar_one()
    try:
        vector_db_total = MilvusChunkStore().stats().get('total_vectors', 0)
    except Exception:
        vector_db_total = 0
    return {'total_uploaded': total_uploaded, 'total_parsed': total_parsed, 'total_qa_calls': total_qa_calls, 'total_reports': total_reports, 'total_graphs': total_graphs, 'total_users': total_users, 'active_users': active_users, 'vector_db_total': vector_db_total}

@router.get('/daily-stats')
async def daily_stats(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    from datetime import datetime, timedelta
    today = datetime.now().date()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    date_set = set(dates)
    
    upload_result = (await db.execute(
        select(func.date(Paper.upload_time).label('date'), func.count().label('cnt'))
        .select_from(Paper)
        .where(func.date(Paper.upload_time).in_(date_set))
        .group_by(func.date(Paper.upload_time))
    )).all()
    upload_map = {str(r.date): r.cnt for r in upload_result}
    
    parse_result = (await db.execute(
        select(func.date(Paper.updated_at).label('date'), func.count().label('cnt'))
        .select_from(Paper)
        .where(func.date(Paper.updated_at).in_(date_set), Paper.parse_status.in_(['completed','indexed']))
        .group_by(func.date(Paper.updated_at))
    )).all()
    parse_map = {str(r.date): r.cnt for r in parse_result}
    
    qa_result = (await db.execute(
        select(func.date(QAMessage.created_at).label('date'), func.count().label('cnt'))
        .select_from(QAMessage)
        .where(func.date(QAMessage.created_at).in_(date_set), QAMessage.role == 'user')
        .group_by(func.date(QAMessage.created_at))
    )).all()
    qa_map = {str(r.date): r.cnt for r in qa_result}
    
    report_result = (await db.execute(
        select(func.date(Report.created_at).label('date'), func.count().label('cnt'))
        .select_from(Report)
        .where(func.date(Report.created_at).in_(date_set))
        .group_by(func.date(Report.created_at))
    )).all()
    report_map = {str(r.date): r.cnt for r in report_result}
    
    return {
        'dates': dates,
        'upload': [upload_map.get(d, 0) for d in dates],
        'parse': [parse_map.get(d, 0) for d in dates],
        'qa': [qa_map.get(d, 0) for d in dates],
        'report': [report_map.get(d, 0) for d in dates]
    }
