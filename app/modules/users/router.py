from datetime import datetime, date, timedelta, timezone
from pathlib import Path
import mimetypes
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import User, LearningDuration
from app.models.entities import BEIJING_TZ
from app.schemas import UserOut
from app.services.audit_service import audit_action

router = APIRouter(prefix='/users', tags=['用户'])
settings = get_settings()

ALLOWED_AVATAR_TYPES = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
    'image/gif': '.gif',
}
MAX_AVATAR_BYTES = 2 * 1024 * 1024
AVATAR_FILENAME_RE = re.compile(r'^\d+\.(jpg|jpeg|png|webp|gif)$', re.IGNORECASE)


def _avatar_public_url(user_id: int, ext: str) -> str:
    return f'{settings.api_v1_prefix}/users/avatars/{user_id}{ext}'


def _clear_user_avatar_files(user_id: int) -> None:
    avatar_dir = Path(settings.avatar_dir)
    if not avatar_dir.exists():
        return
    for old in avatar_dir.glob(f'{user_id}.*'):
        old.unlink(missing_ok=True)


async def _bump_learning_duration(db: AsyncSession, user_id: int) -> int:
    """同一用户同一天仅保留一条记录；合并历史重复行并 +1 分钟。
    时间窗口去重：距离上次更新不足 55 秒时不增加，避免多标签页/频繁刷新导致重复计数。
    """
    today = date.today()
    now = datetime.now(BEIJING_TZ)
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

        # 时间窗口去重：55秒内的重复请求不增加
        if record.updated_at:
            updated_at_aware = record.updated_at if record.updated_at.tzinfo else record.updated_at.replace(tzinfo=BEIJING_TZ)
            if (now - updated_at_aware).total_seconds() < 55:
                return record.duration_minutes

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


@router.post('/me/avatar')
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    content_type = (file.content_type or '').lower()
    ext = ALLOWED_AVATAR_TYPES.get(content_type)
    if not ext:
        raise HTTPException(status_code=400, detail='仅支持 JPG、PNG、WebP、GIF 格式头像')

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail='头像文件为空')
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail='头像文件不能超过 2MB')

    avatar_dir = Path(settings.avatar_dir)
    avatar_dir.mkdir(parents=True, exist_ok=True)
    _clear_user_avatar_files(user.id)

    target = avatar_dir / f'{user.id}{ext}'
    target.write_bytes(data)

    user.avatar_url = _avatar_public_url(user.id, ext)
    await audit_action(
        db,
        user_id=user.id,
        module='users',
        operation_type='upload_avatar',
        content={'avatar_url': user.avatar_url},
    )
    await db.commit()
    return {'message': '头像上传成功', 'avatar_url': user.avatar_url}


@router.delete('/me/avatar')
async def delete_avatar(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user.avatar_url:
        raise HTTPException(status_code=400, detail='当前未设置头像')

    _clear_user_avatar_files(user.id)
    user.avatar_url = None
    await audit_action(
        db,
        user_id=user.id,
        module='users',
        operation_type='delete_avatar',
        content={'user_id': user.id},
    )
    await db.commit()
    return {'message': '头像已移除'}


@router.get('/avatars/{filename}')
async def get_avatar(filename: str):
    if not AVATAR_FILENAME_RE.match(filename):
        raise HTTPException(status_code=404, detail='头像不存在')

    path = Path(settings.avatar_dir) / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail='头像不存在')

    media_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    return FileResponse(path, media_type=media_type)


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
