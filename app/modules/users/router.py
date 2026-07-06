from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import User, LearningDuration
from app.schemas import UserOut

router = APIRouter(prefix='/users', tags=['用户'])


@router.get('/me', response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.post('/heartbeat')
async def heartbeat(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    today = date.today()
    year, week, _ = today.isocalendar()
    week_of_year = f'{year}-W{week:02d}'
    month_of_year = today.strftime('%Y-%m')

    existing = await db.execute(
        select(LearningDuration)
        .where(LearningDuration.user_id == user.id, LearningDuration.record_date == today)
    )
    existing = existing.scalar_one_or_none()

    if existing:
        existing.duration_minutes += 1
    else:
        db.add(LearningDuration(
            user_id=user.id,
            record_date=today,
            duration_minutes=1,
            week_of_year=week_of_year,
            month_of_year=month_of_year,
            year=year,
        ))

    await db.commit()
    return {'message': 'heartbeat received', 'today_minutes': existing.duration_minutes + 1 if existing else 1}


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
