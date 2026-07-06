from __future__ import annotations

from app.db.redis import redis_client

PAUSE_KEY = 'system:paused'


async def is_system_paused() -> bool:
    try:
        val = await redis_client.get(PAUSE_KEY)
        return val in (b'1', '1', 1)
    except Exception:
        return False


async def set_system_paused(paused: bool) -> None:
    if paused:
        await redis_client.set(PAUSE_KEY, '1')
    else:
        await redis_client.delete(PAUSE_KEY)
