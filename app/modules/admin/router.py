from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import require_admin
from app.core.security import hash_password
from app.db.mysql import get_db
from app.models import User
from app.schemas import UserCreateIn, UserUpdateIn
from app.services.audit_service import write_audit
from app.utils.json_utils import dumps, loads
router = APIRouter(prefix='/admin', tags=['管理后台'])

@router.get('/users')
async def list_users(keyword: str | None = None, status: str | None = None, sort_by: str | None = None, sort_order: str = 'desc', db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
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
    sort_map = {'id': User.id, 'created_at': User.created_at, 'last_login_at': User.last_login_at, 'status': User.status}
    if sort_by and sort_by in sort_map:
        order_col = sort_map[sort_by]
        stmt = stmt.order_by(order_col.desc() if sort_order == 'desc' else order_col.asc())
    else:
        stmt = stmt.order_by(User.created_at.desc())
    rows = (await db.execute(stmt.limit(500))).scalars().all()
    return [{'id': x.id, 'username': x.username, 'name': x.name, 'email': x.email, 'phone': x.phone, 'role': x.role, 'status': x.status, 'paper_upload_count': x.paper_upload_count, 'report_generate_count': x.report_generate_count, 'quota': loads(x.quota_json,{}), 'created_at': x.created_at.isoformat() if x.created_at else None, 'last_login_at': x.last_login_at.isoformat() if x.last_login_at else None, 'last_login_ip': x.last_login_ip} for x in rows]

@router.post('/users')
async def create_user(data: UserCreateIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    exists = (await db.execute(select(User).where(or_(User.username == data.username, User.email == data.email if data.email else False, User.phone == data.phone if data.phone else False)))).scalar_one_or_none()
    if exists:
        raise HTTPException(400, '账号、邮箱或手机号已存在')
    user = User(username=data.username, password_hash=hash_password(data.password), name=data.name, email=data.email, phone=data.phone, role=data.role, status=data.status, quota_json=dumps(data.quota or {}))
    db.add(user); await db.flush()
    await write_audit(db, admin.id, 'admin', 'create_user', f'新增用户：{user.username}', risk=1)
    await db.commit(); await db.refresh(user)
    return {'id': user.id, 'message': '已新增用户'}

@router.put('/users/{user_id}')
async def update_user(user_id: int, data: UserUpdateIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    user = await db.get(User, user_id)
    if not user: raise HTTPException(404, '用户不存在')
    values = data.model_dump(exclude_unset=True)
    quota = values.pop('quota', None)
    for k,v in values.items(): setattr(user,k,v)
    if quota is not None: user.quota_json = dumps(quota)
    await write_audit(db, admin.id, 'admin', 'update_user', f'更新用户：{user.username}', risk=1)
    await db.commit(); return {'message':'已更新'}

@router.delete('/users/{user_id}')
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    user = await db.get(User, user_id)
    if not user: raise HTTPException(404, '用户不存在')
    if user.id == admin.id: raise HTTPException(400, '不能删除当前登录管理员')
    await db.delete(user)
    await write_audit(db, admin.id, 'admin', 'delete_user', f'删除用户：{user.username}', risk=1)
    await db.commit(); return {'message': '已删除'}

@router.post('/users/{user_id}/reset-password')
async def admin_reset_password(user_id: int, new_password: str, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    user = await db.get(User, user_id)
    if not user: raise HTTPException(404, '用户不存在')
    user.password_hash = hash_password(new_password)
    await write_audit(db, admin.id, 'admin', 'reset_password', f'管理员重置密码：{user.username}', risk=1)
    await db.commit(); return {'message':'已重置'}

@router.get('/users/export')
async def export_users(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    rows = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    header = 'id,username,name,email,phone,role,status,paper_upload_count,report_generate_count,created_at\n'
    body = ''.join([f'{u.id},{u.username},{u.name or ""},{u.email or ""},{u.phone or ""},{u.role},{u.status},{u.paper_upload_count},{u.report_generate_count},{u.created_at}\n' for u in rows])
    return Response((header+body).encode('utf-8-sig'), media_type='text/csv; charset=utf-8', headers={'Content-Disposition':'attachment; filename="users.csv"'})
