from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.db.mysql import get_db
from app.models import User
from app.schemas import LoginIn, RegisterIn, SendCodeIn, VerifyCodeIn, ResetPasswordIn, TokenOut
from app.services.audit_service import write_audit
from app.services.auth_service import LoginGuard, VerificationCodeService

router = APIRouter(prefix='/auth', tags=['认证'])


@router.post('/verification-code')
async def verification_code(data: SendCodeIn, db: AsyncSession = Depends(get_db)):
    phone = data.phone.strip()
    if data.purpose == 'reset_password':
        user = (
            await db.execute(
                select(User).where(User.phone == phone))).scalar_one_or_none()
        if not user:
            raise HTTPException(404, '该账号未注册')
    return await VerificationCodeService().issue(phone, data.purpose)

# 校验验证码
@router.post("/verify-code")
async def verify_code(data:VerifyCodeIn, db: AsyncSession = Depends(get_db)):
    phone = data.phone.strip()
    token = await VerificationCodeService().verify_and_issue_reset_token(
        phone, 
        data.purpose, 
        data.code
    )
    return {"token": token, "phone": phone}

@router.post('/register', response_model=TokenOut)
async def register(data: RegisterIn, request: Request, db: AsyncSession = Depends(get_db)):
    phone = data.phone.strip()
    await VerificationCodeService().verify(phone, 'register', data.code)
    exists = (
        await db.execute(
            select(User).where(
                User.phone == phone,
            )
        )
    ).scalar_one_or_none()

    if exists:
        raise HTTPException(400, '账号、邮箱或手机号已存在')

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        email=data.email,
        phone=phone,
        role='researcher',
        status='active',
    )
    db.add(user)
    await db.flush()
    await write_audit(
        db,
        user.id,
        'auth',
        'register',
        f'用户注册：{user.username}',
        ip=request.client.host if request.client else None,
    )
    await db.commit()

    token = create_access_token(str(user.id), user.role)
    return TokenOut(
        access_token=token,
        user={'id': user.id, 'username': user.username, 'role': user.role},
    )


@router.post('/login', response_model=TokenOut)
async def login(data: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    guard = LoginGuard()
    await guard.assert_not_locked(data.phone)

    user = (
        await db.execute(
            select(User).where(User.phone == data.phone)
        )
    ).scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        await guard.record_failure(data.phone)
        raise HTTPException(401, '账号或密码错误')

    if user.status != 'active':
        raise HTTPException(403, '账号已被禁用')

    await guard.clear(data.phone)
    token = create_access_token(str(user.id), user.role)

    # last_login_at / audit 不是核心登录路径。失败不能导致登录失败。
    try:
        from datetime import datetime

        user.last_login_ip = request.client.host if request.client else None
        user.last_login_at = datetime.utcnow()
        await write_audit(db, user.id, 'auth', 'login', '用户登录', ip=user.last_login_ip)
        await db.commit()
    except Exception:
        await db.rollback()

    return TokenOut(
        access_token=token,
        user={'id': user.id, 'username': user.username, 'role': user.role},
    )

@router.post('/reset-password')
async def reset_password(data: ResetPasswordIn, db: AsyncSession = Depends(get_db)):
    # 使用token验证身份
    phone = await VerificationCodeService().verify_reset_token(data.token)
    user = (
        await db.execute(
            select(User).where(User.phone == phone))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, '账号不存在')
    user.password_hash = hash_password(data.password)
    await db.commit()
    return {'message': '密码已重置'}
