from __future__ import annotations
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.mysql import AsyncSessionLocal, get_db
from app.models import QAMessage, QASession, User
from app.schemas import QAAskIn
from app.services.quota_service import QuotaService
from app.services.rag_service import RAGService
router = APIRouter(prefix='/qa', tags=['智能问答'])

@router.post('/ask')
async def ask(data: QAAskIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await QuotaService().check_daily_qa(user)
    return await RAGService().ask(db, user.id, data.question, data.paper_ids, data.session_id, data.top_k)

@router.post('/ask-stream')
async def ask_stream(data: QAAskIn, user: User = Depends(get_current_user)):
    await QuotaService().check_daily_qa(user)
    async def gen():
        # 流式生成器内自行管理 db session，避免 FastAPI 依赖注入在
        # StreamingResponse 返回后过早关闭 session。
        async with AsyncSessionLocal() as db:
            async for event in RAGService().ask_stream(db, user.id, data.question, data.paper_ids, data.session_id, data.top_k):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    return StreamingResponse(gen(), media_type='text/event-stream')

@router.get('/sessions')
async def sessions(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(QASession).where(QASession.user_id == user.id).order_by(QASession.updated_at.desc()))).scalars().all()
    return [{'id': x.id, 'title': x.title, 'created_at': x.created_at, 'updated_at': x.updated_at} for x in rows]

@router.get('/sessions/{session_id}/messages')
async def messages(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(QAMessage).where(QAMessage.session_id == session_id).order_by(QAMessage.created_at.asc()))).scalars().all()
    return [{'id': x.id, 'role': x.role, 'content': x.content, 'created_at': x.created_at} for x in rows]
