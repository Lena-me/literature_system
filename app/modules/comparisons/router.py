from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import ComparisonResult, User
from app.schemas import CompareIn, CompareNameIn
from app.services.generation_service import GenerationService
from app.utils.json_utils import loads

router = APIRouter(prefix='/comparisons', tags=['multi-paper comparison'])


def _serialize(obj: ComparisonResult) -> dict:
    return {
        'id': obj.id,
        'name': obj.name,
        'paper_ids': loads(obj.paper_ids, []),
        'result': loads(obj.result_json, {}),
        'created_at': obj.created_at,
    }


@router.post('')
async def compare(
    data: CompareIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        obj = await GenerationService().compare_papers(
            db,
            user.id,
            data.paper_ids,
            data.dimensions,
            data.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize(obj)


@router.post('/suggest-name')
async def suggest_compare_name(
    data: CompareNameIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        name = await GenerationService().suggest_compare_name(
            db,
            user.id,
            data.paper_ids,
            data.dimensions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {'name': name}


@router.get('')
async def list_comparisons(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(ComparisonResult)
            .where(ComparisonResult.user_id == user.id)
            .order_by(ComparisonResult.created_at.desc())
            .limit(50)
        )
    ).scalars().all()

    return [_serialize(x) for x in rows]


@router.get('/{comparison_id}')
async def get_comparison(
    comparison_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = await db.get(ComparisonResult, comparison_id)

    if not obj or obj.user_id != user.id:
        raise HTTPException(status_code=404, detail='Comparison record not found.')

    return _serialize(obj)


@router.delete('/{comparison_id}')
async def delete_comparison(
    comparison_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = await db.get(ComparisonResult, comparison_id)

    if not obj or obj.user_id != user.id:
        raise HTTPException(status_code=404, detail='Comparison record not found.')

    await db.delete(obj)
    await db.commit()

    return {'ok': True}
