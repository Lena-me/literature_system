from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import User, LearningDuration
from app.schemas import UserOut

router = APIRouter(prefix='/users', tags=['用户'])


async def _bump_learning_duration(db: AsyncSession, user_id: int) -> int:
    """同一用户同一天仅保留一条记录；合并历史重复行并 +1 分钟。"""
    today = date.today()
    year, week, _ = today.isocalendar()
    week_of_year = f'{year}-W{week:02d}'
    month_of_year = today.strftime('%Y-%m')

    rows = (
        await db.execute(
            select(LearningDuration)
            .where(LearningDuration.user_id == user_id, LearningDuration.record_date == today)
            .order_by(LearningDuration.id.asc())
            .with_for_update()
        )
    ).scalars().all()

    if rows:
        record = rows[0]
        if len(rows) > 1:
            record.duration_minutes += sum(r.duration_minutes for r in rows[1:])
            for duplicate in rows[1:]:
                await db.delete(duplicate)
        record.duration_minutes += 1
        return record.duration_minutes

    db.add(
        LearningDuration(
            user_id=user_id,
            record_date=today,
            duration_minutes=1,
            week_of_year=week_of_year,
            month_of_year=month_of_year,
            year=year,
        )
    )
    return 1


@router.get('/me', response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.post('/heartbeat')
async def heartbeat(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        today_minutes = await _bump_learning_duration(db, user.id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        today_minutes = await _bump_learning_duration(db, user.id)
        await db.commit()
    return {'message': 'heartbeat received', 'today_minutes': today_minutes}


@router.get('/learning-duration')
async def get_learning_duration(
    period: str = 'today',
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    today = date.today()

    if period == 'today':
        result = await db.execute(
            select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0))
            .where(LearningDuration.user_id == user.id, LearningDuration.record_date == today)
        )
        minutes = result.scalar_one()
        return {'period': 'today', 'minutes': minutes}

    elif period == 'week':
        year, week, _ = today.isocalendar()
        week_of_year = f'{year}-W{week:02d}'
        result = await db.execute(
            select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0))
            .where(LearningDuration.user_id == user.id, LearningDuration.week_of_year == week_of_year)
        )
        minutes = result.scalar_one()
        return {'period': 'week', 'minutes': minutes}

    elif period == 'month':
        month_of_year = today.strftime('%Y-%m')
        result = await db.execute(
            select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0))
            .where(LearningDuration.user_id == user.id, LearningDuration.month_of_year == month_of_year)
        )
        minutes = result.scalar_one()
        return {'period': 'month', 'minutes': minutes}

    elif period == 'year':
        result = await db.execute(
            select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0))
            .where(LearningDuration.user_id == user.id, LearningDuration.year == today.year)
        )
        minutes = result.scalar_one()
        return {'period': 'year', 'minutes': minutes}

    elif period == 'total':
        result = await db.execute(
            select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0))
            .where(LearningDuration.user_id == user.id)
        )
        minutes = result.scalar_one()
        return {'period': 'total', 'minutes': minutes}

    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail='Invalid period. Must be one of: today, week, month, year, total')


@router.get('/learning-duration/all')
async def get_all_learning_duration(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    today = date.today()
    year, week, _ = today.isocalendar()
    week_of_year = f'{year}-W{week:02d}'
    month_of_year = today.strftime('%Y-%m')

    today_result = await db.execute(
        select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0))
        .where(LearningDuration.user_id == user.id, LearningDuration.record_date == today)
    )
    week_result = await db.execute(
        select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0))
        .where(LearningDuration.user_id == user.id, LearningDuration.week_of_year == week_of_year)
    )
    month_result = await db.execute(
        select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0))
        .where(LearningDuration.user_id == user.id, LearningDuration.month_of_year == month_of_year)
    )
    year_result = await db.execute(
        select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0))
        .where(LearningDuration.user_id == user.id, LearningDuration.year == today.year)
    )
    total_result = await db.execute(
        select(func.coalesce(func.sum(LearningDuration.duration_minutes), 0))
        .where(LearningDuration.user_id == user.id)
    )

    return {
        'today': today_result.scalar_one(),
        'week': week_result.scalar_one(),
        'month': month_result.scalar_one(),
        'year': year_result.scalar_one(),
        'total': total_result.scalar_one(),
    }
