from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.mysql import AsyncSessionLocal, celery_db
from app.models import ModelConfig
from app.services.model_config_secrets import resolve_api_key_from_config
from app.services.model_scenarios import DEFAULT_LLM_SCENARIO, scenario_name
from app.utils.json_utils import loads

_CACHE_TTL_SECONDS = 15
_cache_lock = threading.Lock()
_cached_at_by_scenario: dict[str, float] = {}
_cached_config_by_scenario: dict[str, LLMRuntimeConfig] = {}

DEFAULT_LLM_TEMPERATURE = 0.2
DEFAULT_LLM_MAX_TOKENS = 2048


class LLMNotConfiguredError(RuntimeError):
    """指定业务场景未配置可用的大语言模型。"""


@dataclass(frozen=True)
class LLMRuntimeConfig:
    model_name: str
    base_url: str
    api_key: str
    temperature: float
    max_tokens: int
    config_id: int
    scenario: str
    is_primary: bool
    thinking_enabled: bool = False
    reasoning_effort: str | None = None


def _infer_thinking_enabled(model_name: str, cfg: dict) -> bool:
    if 'thinking_enabled' in cfg:
        return bool(cfg.get('thinking_enabled'))
    m = (model_name or '').lower()
    return m.startswith('deepseek-') or 'deepseek' in m


def _infer_reasoning_effort(cfg: dict) -> str | None:
    effort = cfg.get('reasoning_effort')
    if effort is None:
        return None
    text = str(effort).strip().lower()
    return text or None


def normalize_llm_base_url(url: str) -> str:
    u = (url or '').strip().rstrip('/')
    if u.endswith('/chat/completions'):
        u = u[: -len('/chat/completions')].rstrip('/')
    return u


def _from_model_config(row: ModelConfig, settings: Settings) -> LLMRuntimeConfig:
    cfg = loads(row.config_json, {})
    temperature = cfg.get('temperature', DEFAULT_LLM_TEMPERATURE)
    max_tokens = cfg.get('max_tokens', DEFAULT_LLM_MAX_TOKENS)
    try:
        temperature = float(temperature)
    except (TypeError, ValueError):
        temperature = DEFAULT_LLM_TEMPERATURE
    try:
        max_tokens = int(max_tokens)
    except (TypeError, ValueError):
        max_tokens = DEFAULT_LLM_MAX_TOKENS
    base_url = normalize_llm_base_url(row.api_endpoint or '')
    model_name = (row.model_name or '').strip()
    secret = (settings.model_config_secret_key or settings.secret_key or '').strip()
    api_key = resolve_api_key_from_config(cfg, secret)
    return LLMRuntimeConfig(
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        config_id=row.id,
        scenario=row.scenario or DEFAULT_LLM_SCENARIO,
        is_primary=bool(row.is_primary),
        thinking_enabled=_infer_thinking_enabled(model_name, cfg),
        reasoning_effort=_infer_reasoning_effort(cfg),
    )


def _pick_row(rows: list[ModelConfig]) -> ModelConfig | None:
    if not rows:
        return None
    primaries = [r for r in rows if r.is_primary]
    if primaries:
        return sorted(primaries, key=lambda r: (r.updated_at, r.id), reverse=True)[0]
    return sorted(rows, key=lambda r: (r.updated_at, r.id), reverse=True)[0]


def _load_from_db_sync(settings: Settings, scenario: str) -> LLMRuntimeConfig | None:
    with celery_db() as db:
        rows = db.execute(
            select(ModelConfig)
            .where(
                ModelConfig.model_type == 'llm',
                ModelConfig.is_active.is_(True),
                ModelConfig.scenario == scenario,
            )
            .order_by(ModelConfig.is_primary.desc(), ModelConfig.updated_at.desc(), ModelConfig.id.desc())
        ).scalars().all()
        row = _pick_row(list(rows))
        if not row:
            return None
        return _from_model_config(row, settings)


async def _load_from_db_async(settings: Settings, scenario: str) -> LLMRuntimeConfig | None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(ModelConfig)
                .where(
                    ModelConfig.model_type == 'llm',
                    ModelConfig.is_active.is_(True),
                    ModelConfig.scenario == scenario,
                )
                .order_by(ModelConfig.is_primary.desc(), ModelConfig.updated_at.desc(), ModelConfig.id.desc())
            )
        ).scalars().all()
        row = _pick_row(list(rows))
        if not row:
            return None
        return _from_model_config(row, settings)


def invalidate_llm_runtime_cache() -> None:
    global _cached_at_by_scenario, _cached_config_by_scenario
    with _cache_lock:
        _cached_at_by_scenario = {}
        _cached_config_by_scenario = {}


def _resolve_or_raise(db_config: LLMRuntimeConfig | None, scenario: str) -> LLMRuntimeConfig:
    if db_config is None:
        label = scenario_name(scenario) or scenario
        raise LLMNotConfiguredError(f'请在管理后台为「{label}」场景配置并启用大语言模型')
    return db_config


def get_llm_runtime_config(*, scenario: str = DEFAULT_LLM_SCENARIO, force_refresh: bool = False) -> LLMRuntimeConfig:
    settings = get_settings()
    now = time.time()
    with _cache_lock:
        cached_at = _cached_at_by_scenario.get(scenario, 0.0)
        cached = _cached_config_by_scenario.get(scenario)
        if not force_refresh and cached is not None and now - cached_at < _CACHE_TTL_SECONDS:
            return cached

    resolved = _resolve_or_raise(_load_from_db_sync(settings, scenario), scenario)
    with _cache_lock:
        _cached_config_by_scenario[scenario] = resolved
        _cached_at_by_scenario[scenario] = now
    return resolved


async def get_llm_runtime_config_async(
    *,
    scenario: str = DEFAULT_LLM_SCENARIO,
    force_refresh: bool = False,
) -> LLMRuntimeConfig:
    settings = get_settings()
    now = time.time()
    with _cache_lock:
        cached_at = _cached_at_by_scenario.get(scenario, 0.0)
        cached = _cached_config_by_scenario.get(scenario)
        if not force_refresh and cached is not None and now - cached_at < _CACHE_TTL_SECONDS:
            return cached

    resolved = _resolve_or_raise(await _load_from_db_async(settings, scenario), scenario)
    with _cache_lock:
        _cached_config_by_scenario[scenario] = resolved
        _cached_at_by_scenario[scenario] = now
    return resolved


async def try_get_llm_runtime_config_async(
    *,
    scenario: str = DEFAULT_LLM_SCENARIO,
    force_refresh: bool = False,
) -> LLMRuntimeConfig | None:
    try:
        return await get_llm_runtime_config_async(scenario=scenario, force_refresh=force_refresh)
    except LLMNotConfiguredError:
        return None
