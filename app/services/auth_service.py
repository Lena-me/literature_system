from __future__ import annotations
import random
from fastapi import HTTPException
from app.core.config import get_settings
from app.db.redis import redis_client
settings = get_settings()

# 验证码相关功能
class VerificationCodeService:
    def _key(self, phone: str, purpose: str) -> str:
        return f"verification:{purpose}:{phone}"

    # 生成验证码，目前验证码是随机生成的6位数数字
    async def issue(self, phone: str, purpose: str) -> dict:
        code = f"{random.randint(0, 999999):06d}"
        await redis_client.set(self._key(phone, purpose), code, ex=settings.verification_code_ttl_seconds)
        # 目前没有接入短信/邮件网关，因此开发环境直接返回验证码；接入网关后可只返回 message
        return {"message": "验证码已生成，有效期5分钟", "phone": phone, "purpose": purpose, "dev_code": code}

    # 校验验证码
    async def verify(self, phone: str, purpose: str, code: str) -> None:
        expected = await redis_client.get(self._key(phone, purpose))
        # 查不到，验证码应该是过期了或不存在
        if not expected:
            raise HTTPException(400, "验证码不存在或已过期，请重新获取")
        # 不符合
        if str(expected) != str(code):
            raise HTTPException(400, "验证码错误")
        # 验证成功立即删除
        await redis_client.delete(self._key(phone, purpose))

# 安全登录相关功能
class LoginGuard:
    def _fail_key(self, phone: str) -> str:
        return f"login:fail:{phone}"
    def _lock_key(self, phone: str) -> str:
        return f"login:lock:{phone}"

    # 检查账号是否被锁住
    async def assert_not_locked(self, phone: str) -> None:
        ttl = await redis_client.ttl(self._lock_key(phone))
        if ttl and ttl > 0:
            raise HTTPException(403, f"账号已被锁定，请 {ttl//60 + 1} 分钟后重试")

    # 记录失败、锁定的功能
    async def record_failure(self, phone: str) -> None:
        key = self._fail_key(phone)
        count = await redis_client.incr(key)
        await redis_client.expire(key, settings.login_lock_minutes * 60)
        # 达到 login_max_failures 次数就锁定
        if int(count) >= settings.login_max_failures:
            await redis_client.set(self._lock_key(phone), "1", ex=settings.login_lock_minutes * 60)
            await redis_client.delete(key)
            raise HTTPException(403, f"密码连续错误达到{settings.login_max_failures}次，账号已锁定{settings.login_lock_minutes}分钟")
        remain = settings.login_max_failures - int(count)
        raise HTTPException(401, f"账号或密码错误，剩余尝试次数：{remain}")


    async def clear(self, phone: str) -> None:
        await redis_client.delete(self._fail_key(phone), self._lock_key(phone))

