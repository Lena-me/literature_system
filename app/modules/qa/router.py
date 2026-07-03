from __future__ import annotations
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.mysql import AsyncSessionLocal, get_db
from app.models import Paper, QAMessage, QAMessageSource, QASession, QASessionPaper, TextChunk, User
from app.schemas import QAAskIn, SessionCreateIn, SessionUpdateIn
from app.services.quota_service import QuotaService
from app.services.rag_service import get_rag_service
from app.services.source_enrichment import enrich_qa_sources
from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.utils.session_title import fallback_session_title, is_default_session_title, sanitize_session_title
router = APIRouter(prefix='/qa', tags=['智能问答'])

@router.post('/ask')
async def ask(data: QAAskIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await QuotaService().check_daily_qa(user)
    return await get_rag_service().ask(db, user.id, data.question, data.paper_ids, data.session_id, data.top_k)

@router.post('/ask-stream')
async def ask_stream(data: QAAskIn, user: User = Depends(get_current_user)):
    await QuotaService().check_daily_qa(user)
    async def gen():
        # 流式生成器内自行管理 db session，避免 FastAPI 依赖注入在
        # StreamingResponse 返回后过早关闭 session。
        async with AsyncSessionLocal() as db:
            async for event in get_rag_service().ask_stream(db, user.id, data.question, data.paper_ids, data.session_id, data.top_k):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    return StreamingResponse(
        gen(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache, no-transform',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )

# ========== Session CRUD ==========

@router.post('/sessions')
async def create_session(data: SessionCreateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """新建会话，可选的初始挂载文献"""
    session = QASession(user_id=user.id, title=data.title or '新对话')
    db.add(session)
    await db.flush()
    if data.paper_ids:
        await _set_session_papers(db, session.id, data.paper_ids)
    await db.commit()
    await db.refresh(session)
    papers = await _get_session_papers(db, session.id)
    return _session_detail(session, papers)

@router.get('/sessions/{session_id}')
async def get_session(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """获取会话详情，包含挂载的文献列表"""
    session = await db.get(QASession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, '会话不存在')
    papers = await _get_session_papers(db, session_id)
    return _session_detail(session, papers)

@router.patch('/sessions/{session_id}')
async def update_session(session_id: int, data: SessionUpdateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """更新会话：重命名 / 增减挂载文献"""
    session = await db.get(QASession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, '会话不存在')
    if data.title is not None:
        session.title = data.title
    if data.add_paper_ids:
        for pid in data.add_paper_ids:
            exists = await db.execute(
                select(QASessionPaper).where(QASessionPaper.session_id == session_id, QASessionPaper.paper_id == pid)
            )
            if not exists.scalar_one_or_none():
                db.add(QASessionPaper(session_id=session_id, paper_id=pid))
    if data.remove_paper_ids:
        await db.execute(
            delete(QASessionPaper).where(
                QASessionPaper.session_id == session_id,
                QASessionPaper.paper_id.in_(data.remove_paper_ids),
            )
        )
    await db.commit()
    await db.refresh(session)
    papers = await _get_session_papers(db, session_id)
    return _session_detail(session, papers)

@router.delete('/sessions/{session_id}')
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """删除会话（级联删除消息和关联）"""
    session = await db.get(QASession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, '会话不存在')
    await db.delete(session)
    await db.commit()
    return {'message': '会话已删除'}

# ========== 历史会话列表 ==========

@router.get('/sessions')
async def sessions(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(QASession).where(QASession.user_id == user.id).order_by(QASession.updated_at.desc())
    )).scalars().all()

    if not rows:
        return []

    session_ids = [s.id for s in rows]

    # ★ 批量查询：一次查出所有会话的文献映射
    paper_rows = (await db.execute(
        select(QASessionPaper.session_id, QASessionPaper.paper_id)
        .where(QASessionPaper.session_id.in_(session_ids))
    )).all()
    paper_map: dict[int, list[int]] = {}
    for sid, pid in paper_rows:
        paper_map.setdefault(sid, []).append(pid)

    # ★ 批量查询：用子查询取每个会话的最后一条消息
    from sqlalchemy import func
    sub = (
        select(QAMessage.session_id, func.max(QAMessage.created_at).label('max_ts'))
        .where(QAMessage.session_id.in_(session_ids))
        .group_by(QAMessage.session_id)
        .subquery()
    )
    msg_rows = (await db.execute(
        select(QAMessage.session_id, QAMessage.content)
        .join(sub, (QAMessage.session_id == sub.c.session_id) & (QAMessage.created_at == sub.c.max_ts))
    )).all()
    msg_map: dict[int, str] = {sid: (content or '')[:100] for sid, content in msg_rows}

    result = []
    for s in rows:
        pids = paper_map.get(s.id, [])
        result.append({
            'id': s.id, 'title': s.title,
            'paper_count': len(pids), 'paper_ids': pids,
            'last_message_preview': msg_map.get(s.id, ''),
            'created_at': s.created_at, 'updated_at': s.updated_at,
        })
    return result

# ========== 消息历史 ==========

@router.get('/sessions/{session_id}/messages')
async def messages(
    session_id: int,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取会话消息历史。limit=0 表示不限制"""
    session = await db.get(QASession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, '会话不存在')
    q = select(QAMessage).where(QAMessage.session_id == session_id).order_by(QAMessage.created_at.asc())
    if limit > 0:
        q = q.limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()

    # ★ 批量查询所有消息的来源引用
    message_ids = [x.id for x in rows]
    sources_map: dict[int, list[dict]] = {mid: [] for mid in message_ids}
    if message_ids:
        src_q = (
            select(QAMessageSource, TextChunk.chunk_text)
            .outerjoin(TextChunk, QAMessageSource.chunk_id == TextChunk.id)
            .where(QAMessageSource.message_id.in_(message_ids))
        )
        src_rows = (await db.execute(src_q)).all()
        for src, chunk_text in src_rows:
            sources_map[src.message_id].append({
                'chunk_id': src.chunk_id,
                'paper_id': src.paper_id,
                'page_number': src.page_number,
                'section_title': src.section_title,
                'text': chunk_text or src.snippet,
                'snippet': src.snippet,
                'similarity_score': src.similarity_score,
                'rerank_score': src.similarity_score,
            })

    msg_by_id = {x.id: x for x in rows}

    for mid in message_ids:
        if sources_map[mid]:
            msg = msg_by_id.get(mid)
            answer_text = msg.content if msg and msg.role == 'assistant' else None
            sources_map[mid] = await enrich_qa_sources(db, sources_map[mid], answer_text=answer_text)

    return [
        {
            'id': x.id,
            'role': x.role,
            'content': x.content,
            'created_at': x.created_at,
            'sources': sources_map.get(x.id, []),
        }
        for x in rows
    ]

# ========== 自动生成标题 ==========

class GenerateTitleIn(PydanticBaseModel):
    first_message: str

@router.post('/sessions/{session_id}/generate-title')
async def generate_title(session_id: int, data: GenerateTitleIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """根据首条消息自动生成会话标题"""
    import logging
    logger = logging.getLogger(__name__)
    session = await db.get(QASession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, '会话不存在')

    first_message = (data.first_message or '').strip()
    fallback = fallback_session_title(first_message)

    try:
        llm = OpenAICompatibleLLM()
        raw = await llm.async_chat(
            messages=[
                {
                    'role': 'system',
                    'content': (
                        '你是会话标题提炼助手。根据用户提问生成不超过12个字的极简中文标题。'
                        '只输出标题本身，不要引号、编号、Markdown、解释或标点结尾。'
                    ),
                },
                {'role': 'user', 'content': f'用户提问：{first_message}'},
            ],
            temperature=0.2,
            max_tokens=128,
            content_only=True,
        )
        title = sanitize_session_title(raw, fallback=fallback, max_len=20)
        logger.info('[generate-title] session_id=%s raw=%r title=%r fallback=%r', session_id, raw, title, fallback)
        if title and not is_default_session_title(title):
            session.title = title
            await db.commit()
            await db.refresh(session)
        elif fallback and not is_default_session_title(fallback):
            session.title = fallback
            await db.commit()
            await db.refresh(session)
            logger.info('[generate-title] 使用首条消息兜底标题: %r', fallback)
        else:
            logger.warning('[generate-title] 标题无效，保持原标题: %s', session.title)
        return {'title': session.title}
    except Exception as e:
        logger.warning('[generate-title] 生成失败: %s', e, exc_info=True)
        if fallback and not is_default_session_title(fallback) and is_default_session_title(session.title):
            session.title = fallback
            await db.commit()
            await db.refresh(session)
            logger.info('[generate-title] LLM 失败后使用兜底标题: %r', fallback)
        return {'title': session.title}

# ========== 推荐问题 ==========

@router.get('/sessions/{session_id}/suggested-questions')
async def suggested_questions(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """根据会话挂载的文献生成推荐问题"""
    session = await db.get(QASession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, '会话不存在')
    return await get_rag_service().suggest_questions(db, session_id)

# ========== 内部辅助函数 ==========

async def _get_session_paper_ids(db: AsyncSession, session_id: int) -> list[int]:
    rows = (await db.execute(
        select(QASessionPaper.paper_id).where(QASessionPaper.session_id == session_id)
    )).scalars().all()
    return list(rows)

async def _get_session_papers(db: AsyncSession, session_id: int) -> list[dict]:
    pids = await _get_session_paper_ids(db, session_id)
    if not pids:
        return []
    papers = (await db.execute(select(Paper).where(Paper.id.in_(pids)))).scalars().all()
    return [{'id': p.id, 'title': p.title or p.original_filename, 'original_filename': p.original_filename, 'parse_status': p.parse_status, 'authors': p.authors, 'publication_year': p.publication_year} for p in papers]

async def _set_session_papers(db: AsyncSession, session_id: int, paper_ids: list[int]) -> None:
    for pid in paper_ids:
        db.add(QASessionPaper(session_id=session_id, paper_id=pid))

def _session_detail(session: QASession, papers: list[dict]) -> dict:
    return {
        'id': session.id, 'user_id': session.user_id, 'title': session.title,
        'papers': papers, 'paper_count': len(papers),
        'created_at': session.created_at, 'updated_at': session.updated_at,
    }
