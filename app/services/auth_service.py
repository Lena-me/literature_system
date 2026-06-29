from __future__ import annotations
import random
from fastapi import HTTPException
from app.core.config import get_settings
from app.db.redis import redis_client
settings = get_settings()

class VerificationCodeService:
    def _key(self, account: str, purpose: str) -> str:
        return f"verification:{purpose}:{account}"

    async def issue(self, account: str, purpose: str) -> dict:
        code = f"{random.randint(0, 999999):06d}"
        await redis_client.set(self._key(account, purpose), code, ex=settings.verification_code_ttl_seconds)
        # 当前工程没有接入短信/邮件网关，因此开发环境直接返回验证码；接入网关后可只返回 message。
        return {"message": "验证码已生成，有效期5分钟", "account": account, "purpose": purpose, "dev_code": code}

    async def verify(self, account: str, purpose: str, code: str) -> None:
        expected = await redis_client.get(self._key(account, purpose))
        if not expected:
            raise HTTPException(400, "验证码不存在或已过期，请重新获取")
        if str(expected) != str(code):
            raise HTTPException(400, "验证码错误")
        await redis_client.delete(self._key(account, purpose))

class LoginGuard:
    def _fail_key(self, account: str) -> str:
        return f"login:fail:{account}"
    def _lock_key(self, account: str) -> str:
        return f"login:lock:{account}"

    async def assert_not_locked(self, account: str) -> None:
        ttl = await redis_client.ttl(self._lock_key(account))
        if ttl and ttl > 0:
            raise HTTPException(403, f"账号已被锁定，请 {ttl//60 + 1} 分钟后重试")

    async def record_failure(self, account: str) -> None:
        key = self._fail_key(account)
        count = await redis_client.incr(key)
        await redis_client.expire(key, settings.login_lock_minutes * 60)
        if int(count) >= settings.login_max_failures:
            await redis_client.set(self._lock_key(account), "1", ex=settings.login_lock_minutes * 60)
            await redis_client.delete(key)
            raise HTTPException(403, f"密码连续错误达到{settings.login_max_failures}次，账号已锁定{settings.login_lock_minutes}分钟")
        remain = settings.login_max_failures - int(count)
        raise HTTPException(401, f"账号或密码错误，剩余尝试次数：{remain}")

    async def clear(self, account: str) -> None:
        await redis_client.delete(self._fail_key(account), self._lock_key(account))
