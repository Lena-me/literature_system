from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.core.security import hash_password
from app.db.mysql import get_db
from app.models import AuditLog, Paper, ParseTask, User
from app.schemas import SystemPauseIn, TaskBatchCancelIn, TaskBatchRetryIn, UserCreateIn, UserUpdateIn
from app.schemas.admin import (
    AdminAuditLogListOut,
    AdminAuditLogOut,
    AdminOverviewOut,
    AdminTaskListOut,
    AdminTaskOut,
    AdminTaskStatsOut,
    AdminUserDetailOut,
    AdminUserOut,
)
from app.services.admin_logs_service import audit_operation_summary, list_audit_logs, list_vector_snapshots
from app.services.admin_overview_service import build_models_monitor, build_overview
from app.services.model_scenarios import MODEL_SCENARIOS
from app.services.audit_service import write_audit
from app.services.quota_service import quota_of
from app.services.system_pause import is_system_paused, set_system_paused
from app.utils.admin_privacy import mask_email, mask_phone
from app.utils.json_utils import dumps, loads
from app.workers.celery_app import celery_app

router = APIRouter(prefix='/admin', tags=['管理后台'])


def _task_item(x: ParseTask, *, username: str | None = None, paper_label: str | None = None) -> dict:
    return AdminTaskOut(
        id=x.id,
        username=username or '未知用户',
        paper_label=paper_label or '未知文献',
        task_type=x.task_type,
        status=x.status,
        priority=x.priority,
        queue_position=x.queue_position,
        start_time=x.start_time,
        end_time=x.end_time,
        duration_ms=x.duration_ms,
        retry_count=x.retry_count,
        error_log=x.error_log,
        created_at=x.created_at,
    ).model_dump()


async def _tasks_for_admin(db: AsyncSession, rows: list[ParseTask]) -> list[dict]:
    if not rows:
        return []
    user_ids = {int(x.user_id) for x in rows if x.user_id}
    paper_ids = {int(x.paper_id) for x in rows if x.paper_id}
    users: dict[int, str] = {}
    papers: dict[int, str] = {}
    if user_ids:
        user_rows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users = {u.id: u.username for u in user_rows}
    if paper_ids:
        paper_rows = (await db.execute(select(Paper).where(Paper.id.in_(paper_ids)))).scalars().all()
        papers = {
            p.id: (p.original_filename or p.title or '未知文献')
            for p in paper_rows
        }
    return [
        _task_item(
            task,
            username=users.get(task.user_id),
            paper_label=papers.get(task.paper_id, '未知文献'),
        )
        for task in rows
    ]


@router.get('/overview', response_model=AdminOverviewOut)
async def admin_overview(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    return AdminOverviewOut.model_validate(await build_overview(db)).model_dump()


@router.get('/logs/audit', response_model=AdminAuditLogListOut)
async def admin_audit_logs(
    page: int = 1,
    size: int = 20,
    user_id: int | None = None,
    risk_flag: bool | None = None,
    keyword: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return await list_audit_logs(
        db,
        page=page,
        size=size,
        user_id=user_id,
        risk_flag=risk_flag,
        keyword=keyword,
        start_at=start_at,
        end_at=end_at,
    )


@router.get('/vector/snapshots')
async def admin_vector_snapshots(
    days: int = 7,
    limit: int = 168,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return await list_vector_snapshots(db, days=days, limit=limit)


@router.get('/models/monitor')
async def admin_models_monitor(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    return await build_models_monitor(db)


@router.get('/models/scenarios')
async def admin_model_scenarios(admin: User = Depends(require_admin)):
    return MODEL_SCENARIOS


@router.get('/system/pause')
async def get_system_pause(admin: User = Depends(require_admin)):
    paused = await is_system_paused()
    return {'paused': paused}


@router.post('/system/pause')
async def set_system_pause(
    data: SystemPauseIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    await set_system_paused(data.paused)
    action = 'pause_system' if data.paused else 'resume_system'
    label = '全局暂停系统' if data.paused else '恢复系统运行'
    await write_audit(db, admin.id, 'admin', action, label, risk=2)
    await db.commit()
    return {'paused': data.paused, 'message': label}


async def _task_status_stats(db: AsyncSession) -> dict:
    rows = (
        await db.execute(select(ParseTask.status, func.count()).group_by(ParseTask.status))
    ).all()
    counts = {str(r[0]): int(r[1]) for r in rows}
    return AdminTaskStatsOut(
        total=sum(counts.values()),
        running=counts.get('running', 0),
        failed=counts.get('failed', 0),
        queued=counts.get('queued', 0),
        completed=counts.get('completed', 0),
        cancelled=counts.get('cancelled', 0),
    ).model_dump()


@router.get('/tasks', response_model=AdminTaskListOut)
async def admin_list_tasks(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    base = select(ParseTask)
    if status:
        base = base.where(ParseTask.status == status)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(
            base.order_by(ParseTask.priority.asc(), ParseTask.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return AdminTaskListOut(
        items=await _tasks_for_admin(db, list(rows)),
        total=int(total or 0),
        page=page,
        page_size=page_size,
        stats=await _task_status_stats(db),
    ).model_dump()


@router.post('/tasks/batch-retry')
async def admin_batch_retry(
    data: TaskBatchRetryIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    rows = (await db.execute(select(ParseTask).where(ParseTask.id.in_(data.task_ids)))).scalars().all()
    retried = []
    for task in rows:
        if task.status in {'failed', 'cancelled'}:
            task.status = 'queued'
            task.error_log = None
            task.retry_count += 1
            celery_app.send_task(
                'app.workers.tasks.process_paper_pipeline',
                args=[task.paper_id],
                queue='paper_tasks',
            )
            retried.append(task.id)
    await write_audit(db, admin.id, 'admin', 'batch_retry_tasks', f'批量重试 {len(retried)} 个任务', risk=1)
    await db.commit()
    return {'retried_task_ids': retried}


@router.post('/tasks/batch-cancel')
async def admin_batch_cancel(
    data: TaskBatchCancelIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    rows = (await db.execute(select(ParseTask).where(ParseTask.id.in_(data.task_ids)))).scalars().all()
    cancelled = []
    for task in rows:
        if task.status not in {'completed', 'failed', 'cancelled'}:
            task.status = 'cancelled'
            cancelled.append(task.id)
    await write_audit(db, admin.id, 'admin', 'batch_cancel_tasks', f'批量终止 {len(cancelled)} 个任务', risk=2)
    await db.commit()
    return {'cancelled_task_ids': cancelled}


@router.get('/users/{user_id}/detail', response_model=AdminUserDetailOut)
async def user_detail(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, '用户不存在')
    logs = (
        await db.execute(
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(10)
        )
    ).scalars().all()
    return AdminUserDetailOut(
        user=AdminUserOut(
            id=user.id,
            username=user.username,
            name=user.name,
            email=user.email,
            phone=user.phone,
            role=user.role,
            status=user.status,
            paper_upload_count=user.paper_upload_count,
            report_generate_count=user.report_generate_count,
            quota=quota_of(user),
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            last_login_ip=user.last_login_ip,
        ),
        audit_logs=[
            AdminAuditLogOut(
                module=x.module,
                operation_type=x.operation_type,
                operation_summary=audit_operation_summary(
                    x.module,
                    x.operation_type,
                    content_raw=x.operation_content,
                ),
                operation_result=x.operation_result,
                risk_flag=x.risk_flag,
                created_at=x.created_at,
            )
            for x in logs
        ],
    ).model_dump()


@router.get('/users', response_model=list[AdminUserOut])
async def list_users(
    keyword: str | None = None,
    status: str | None = None,
    sort_by: str | None = None,
    sort_order: str = 'desc',
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    stmt = select(User)
    if keyword:
        if keyword.isdigit():
            if len(keyword) == 11:
                stmt = stmt.where(User.phone == keyword)
            else:
                stmt = stmt.where(User.id == int(keyword))
        else:
            stmt = stmt.where(User.username.like(f'%{keyword}%'))
    if status:
        stmt = stmt.where(User.status == status)
    sort_map = {
        'id': User.id,
        'created_at': User.created_at,
        'last_login_at': User.last_login_at,
        'status': User.status,
    }
    if sort_by and sort_by in sort_map:
        order_col = sort_map[sort_by]
        stmt = stmt.order_by(order_col.desc() if sort_order == 'desc' else order_col.asc())
    else:
        stmt = stmt.order_by(User.created_at.desc())
    rows = (await db.execute(stmt.limit(500))).scalars().all()
    return [
        AdminUserOut(
            id=x.id,
            username=x.username,
            name=x.name,
            email=x.email,
            phone=x.phone,
            role=x.role,
            status=x.status,
            paper_upload_count=x.paper_upload_count,
            report_generate_count=x.report_generate_count,
            quota=loads(x.quota_json, {}),
            created_at=x.created_at,
            last_login_at=x.last_login_at,
            last_login_ip=x.last_login_ip,
        ).model_dump()
        for x in rows
    ]


@router.post('/users')
async def create_user(
    data: UserCreateIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    exists = (
        await db.execute(
            select(User).where(
                or_(
                    User.username == data.username,
                    User.email == data.email if data.email else False,
                    User.phone == data.phone if data.phone else False,
                )
            )
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(400, '账号、邮箱或手机号已存在')
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        name=data.name,
        email=data.email,
        phone=data.phone,
        role=data.role,
        status=data.status,
        quota_json=dumps(data.quota or {}),
    )
    db.add(user)
    await db.flush()
    await write_audit(db, admin.id, 'admin', 'create_user', f'新增用户：{user.username}', risk=1)
    await db.commit()
    await db.refresh(user)
    return {'id': user.id, 'message': '已新增用户'}


@router.put('/users/{user_id}')
async def update_user(
    user_id: int,
    data: UserUpdateIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, '用户不存在')
    values = data.model_dump(exclude_unset=True)
    quota = values.pop('quota', None)
    for k, v in values.items():
        setattr(user, k, v)
    if quota is not None:
        user.quota_json = dumps(quota)
    await write_audit(db, admin.id, 'admin', 'update_user', f'更新用户：{user.username}', risk=1)
    await db.commit()
    return {'message': '已更新'}


@router.delete('/users/{user_id}')
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, '用户不存在')
    if user.id == admin.id:
        raise HTTPException(400, '不能删除当前登录管理员')
    await db.delete(user)
    await write_audit(db, admin.id, 'admin', 'delete_user', f'删除用户：{user.username}', risk=1)
    await db.commit()
    return {'message': '已删除'}


@router.post('/users/{user_id}/reset-password')
async def admin_reset_password(
    user_id: int,
    new_password: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, '用户不存在')
    user.password_hash = hash_password(new_password)
    await write_audit(db, admin.id, 'admin', 'reset_password', f'管理员重置密码：{user.username}', risk=1)
    await db.commit()
    return {'message': '已重置'}


@router.get('/users/export')
async def export_users(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    rows = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    header = 'id,username,name,email,phone,role,status,paper_upload_count,report_generate_count,created_at\n'
    body = ''.join(
        [
            f'{u.id},{u.username},{u.name or ""},'
            f'{mask_email(u.email or "") or ""},{mask_phone(u.phone or "") or ""},'
            f'{u.role},{u.status},{u.paper_upload_count},{u.report_generate_count},{u.created_at}\n'
            for u in rows
        ]
    )
    return Response(
        (header + body).encode('utf-8-sig'),
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="users.csv"'},
    )
