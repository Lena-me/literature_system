from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.mysql import AsyncSessionLocal, celery_db
from app.models import ModelConfig
from app.utils.json_utils import loads

_CACHE_TTL_SECONDS = 15
_cache_lock = threading.Lock()
_cached_at = 0.0
_cached_config: LLMRuntimeConfig | None = None


@dataclass(frozen=True)
class LLMRuntimeConfig:
    model_name: str
    base_url: str
    api_key: str
    temperature: float
    max_tokens: int
    source: str  # db | env
    config_id: int | None = None


def normalize_llm_base_url(url: str) -> str:
    """去掉末尾 /chat/completions，避免拼出重复路径。"""
    u = (url or '').strip().rstrip('/')
    if u.endswith('/chat/completions'):
        u = u[: -len('/chat/completions')].rstrip('/')
    return u


def _from_settings(settings: Settings) -> LLMRuntimeConfig:
    return LLMRuntimeConfig(
        model_name=(settings.llm_model or '').strip(),
        base_url=normalize_llm_base_url(settings.llm_base_url),
        api_key=(settings.llm_api_key or '').strip(),
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        source='env',
        config_id=None,
    )


def _from_model_config(row: ModelConfig, settings: Settings) -> LLMRuntimeConfig:
    cfg = loads(row.config_json, {})
    temperature = cfg.get('temperature', settings.llm_temperature)
    max_tokens = cfg.get('max_tokens', settings.llm_max_tokens)
    try:
        temperature = float(temperature)
    except (TypeError, ValueError):
        temperature = settings.llm_temperature
    try:
        max_tokens = int(max_tokens)
    except (TypeError, ValueError):
        max_tokens = settings.llm_max_tokens
    base_url = normalize_llm_base_url(row.api_endpoint or settings.llm_base_url or '')
    return LLMRuntimeConfig(
        model_name=(row.model_name or '').strip(),
        base_url=base_url,
        api_key=(settings.llm_api_key or '').strip(),
        temperature=temperature,
        max_tokens=max_tokens,
        source='db',
        config_id=row.id,
    )


def _load_from_db_sync(settings: Settings) -> LLMRuntimeConfig | None:
    with celery_db() as db:
        row = db.execute(
            select(ModelConfig)
            .where(ModelConfig.model_type == 'llm', ModelConfig.is_active.is_(True))
            .order_by(ModelConfig.updated_at.desc(), ModelConfig.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if not row:
            return None
        return _from_model_config(row, settings)


async def _load_from_db_async(settings: Settings) -> LLMRuntimeConfig | None:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(ModelConfig)
                .where(ModelConfig.model_type == 'llm', ModelConfig.is_active.is_(True))
                .order_by(ModelConfig.updated_at.desc(), ModelConfig.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not row:
            return None
        return _from_model_config(row, settings)


def invalidate_llm_runtime_cache() -> None:
    global _cached_at, _cached_config
    with _cache_lock:
        _cached_at = 0.0
        _cached_config = None


def get_llm_runtime_config(*, force_refresh: bool = False) -> LLMRuntimeConfig:
    global _cached_at, _cached_config
    settings = get_settings()
    now = time.time()
    with _cache_lock:
        if (
            not force_refresh
            and _cached_config is not None
            and now - _cached_at < _CACHE_TTL_SECONDS
        ):
            return _cached_config

    db_config = _load_from_db_sync(settings)
    resolved = db_config or _from_settings(settings)
    _cached_config = resolved
    _cached_at = now
    return resolved


async def get_llm_runtime_config_async(*, force_refresh: bool = False) -> LLMRuntimeConfig:
    global _cached_at, _cached_config
    settings = get_settings()
    now = time.time()
    with _cache_lock:
        if (
            not force_refresh
            and _cached_config is not None
            and now - _cached_at < _CACHE_TTL_SECONDS
        ):
            return _cached_config

    db_config = await _load_from_db_async(settings)
    resolved = db_config or _from_settings(settings)
    _cached_config = resolved
    _cached_at = now
    return resolved
