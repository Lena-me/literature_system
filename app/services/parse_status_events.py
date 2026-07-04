from __future__ import annotations

import json
import logging

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

TERMINAL_PARSE_STATUSES = frozenset({'completed', 'indexed', 'failed', 'deleted'})


def channel_for_user(user_id: int) -> str:
    return f'paper:parse:user:{user_id}'


def publish_parse_status(
    user_id: int,
    paper_id: int,
    parse_status: str,
    *,
    title: str | None = None,
) -> None:
    """Celery / 同步上下文：经 Redis Pub/Sub 推送解析状态给 SSE 订阅端。"""
    settings = get_settings()
    payload = json.dumps(
        {
            'type': 'parse_status',
            'paper_id': paper_id,
            'parse_status': parse_status,
            'title': title,
        },
        ensure_ascii=False,
    )
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        receivers = client.publish(channel_for_user(user_id), payload)
        logger.debug(
            'parse_status published user=%s paper=%s status=%s receivers=%s',
            user_id,
            paper_id,
            parse_status,
            receivers,
        )
    except Exception as exc:
        logger.warning('parse_status publish failed paper=%s: %s', paper_id, exc)
    finally:
        client.close()
