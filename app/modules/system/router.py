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
    try:
        vector_db_total = MilvusChunkStore().stats().get('total_vectors', 0)
    except Exception:
        vector_db_total = 0
    return {'total_uploaded': total_uploaded, 'total_parsed': total_parsed, 'total_qa_calls': total_qa_calls, 'total_reports': total_reports, 'total_graphs': total_graphs, 'vector_db_total': vector_db_total}
