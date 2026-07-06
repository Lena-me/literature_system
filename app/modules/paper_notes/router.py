from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import Paper, User, UserPaperNote
from app.schemas import PaperNoteCreateIn, PaperNoteUpdateIn

router = APIRouter(prefix='/paper-notes', tags=['文献笔记'])
logger = logging.getLogger(__name__)


def _is_missing_notes_table(exc: Exception) -> bool:
    raw = str(exc).lower()
    if 'user_paper_notes' not in raw:
        return False
    return 'doesn\'t exist' in raw or 'does not exist' in raw or '1146' in raw or 'undefined table' in raw


def _serialize_note(note: UserPaperNote) -> dict:
    return {
        'id': note.id,
        'paper_id': note.paper_id,
        'page_number': note.page_number,
        'bbox': note.bbox,
        'selected_text': note.selected_text,
        'note_content': note.note_content,
        'highlight_color': note.highlight_color,
        'created_at': note.created_at,
        'updated_at': note.updated_at,
    }


async def _get_owned_paper(db: AsyncSession, user: User, paper_id: int) -> Paper:
    paper = await db.get(Paper, paper_id)
    if not paper or paper.user_id != user.id or paper.is_deleted:
        raise HTTPException(status_code=404, detail='文献不存在')
    return paper


async def _get_owned_note(db: AsyncSession, user: User, note_id: int) -> UserPaperNote:
    note = await db.get(UserPaperNote, note_id)
    if not note or note.user_id != user.id:
        raise HTTPException(status_code=404, detail='笔记不存在')
    return note


@router.get('')
async def list_notes(
    paper_id: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_paper(db, user, paper_id)
    try:
        rows = (
            await db.execute(
                select(UserPaperNote)
                .where(UserPaperNote.user_id == user.id, UserPaperNote.paper_id == paper_id)
                .order_by(UserPaperNote.page_number.asc(), UserPaperNote.created_at.asc())
            )
        ).scalars().all()
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_notes_table(exc):
            logger.warning('user_paper_notes table is missing; returning empty notes for paper_id=%s', paper_id)
            await db.rollback()
            return []
        raise
    return [_serialize_note(row) for row in rows]


@router.post('')
async def create_note(
    data: PaperNoteCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_paper(db, user, data.paper_id)
    obj = UserPaperNote(
        user_id=user.id,
        paper_id=data.paper_id,
        page_number=data.page_number,
        bbox=[rect.model_dump() for rect in data.bbox],
        selected_text=data.selected_text.strip(),
        note_content=(data.note_content or '').strip() or None,
        highlight_color=data.highlight_color or '#FFEB3B',
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _serialize_note(obj)


@router.put('/{note_id}')
async def update_note(
    note_id: int,
    data: PaperNoteUpdateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    note = await _get_owned_note(db, user, note_id)
    if data.note_content is not None:
        note.note_content = data.note_content.strip() or None
    if data.highlight_color is not None:
        note.highlight_color = data.highlight_color
    await db.commit()
    await db.refresh(note)
    return _serialize_note(note)


@router.delete('/{note_id}')
async def delete_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    note = await _get_owned_note(db, user, note_id)
    await db.delete(note)
    await db.commit()
    return {'message': 'deleted'}
