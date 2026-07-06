from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.dependencies import require_admin
from app.db.mysql import get_db
from app.integrations.llm.runtime_config import (
    DEFAULT_LLM_SCENARIO,
    invalidate_llm_runtime_cache,
    try_get_llm_runtime_config_async,
)
from app.models import ModelConfig, User
from app.schemas import ModelConfigIn
from app.services.model_config_secrets import (
    merge_config_for_update,
    prepare_config_for_storage,
    sanitize_config_for_response,
)
from app.services.model_config_service import (
    demote_scenario_primary,
    serialize_model_config_row,
    validate_llm_scenario_fields,
)
from app.services.model_monitor_service import attach_today_stats, build_model_detail
from app.utils.json_utils import dumps, loads

router = APIRouter(prefix='/model-configs', tags=['模型管理'])


class ModelConfigUpdateIn(BaseModel):
    model_type: Literal['parse', 'vector', 'reranker', 'llm'] | None = None
    model_name: str | None = None
    version: str | None = None
    api_endpoint: str | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None
    scenario: Literal['parse', 'qa', 'report', 'tagging'] | None = None
    is_primary: bool | None = None


def _encryption_secret(settings: Settings) -> str:
    return (settings.model_config_secret_key or settings.secret_key or '').strip()


def _require_secret(settings: Settings) -> str:
    secret = _encryption_secret(settings)
    if not secret:
        raise HTTPException(400, '未配置 MODEL_CONFIG_SECRET_KEY 或 SECRET_KEY，无法保存 API Key')
    return secret


def _serialize_row(x: ModelConfig, settings: Settings) -> dict:
    secret = _encryption_secret(settings)
    config = sanitize_config_for_response(loads(x.config_json, {}), secret)
    return serialize_model_config_row(x, config)


def _prepare_stored_config(data_config: dict | None, settings: Settings) -> dict:
    incoming = dict(data_config or {})
    if incoming.get('api_key'):
        secret = _require_secret(settings)
        return prepare_config_for_storage(incoming, secret)
    return prepare_config_for_storage(incoming, _encryption_secret(settings))


def _merge_config_payload(old_cfg: dict, incoming: dict | None, settings: Settings) -> dict:
    inc = dict(incoming or {})
    if inc.get('api_key'):
        secret = _require_secret(settings)
        return merge_config_for_update(old_cfg, inc, secret)
    return merge_config_for_update(old_cfg, inc, _encryption_secret(settings))


def _has_api_key(stored_config: dict) -> bool:
    return bool(stored_config.get('api_key'))


async def _apply_llm_routing(
    db: AsyncSession,
    *,
    obj: ModelConfig,
    scenario: str,
    is_primary: bool,
) -> None:
    obj.scenario = scenario
    obj.is_primary = is_primary
    cfg = loads(obj.config_json, {})
    cfg['route_role'] = 'primary' if is_primary else 'fallback'
    obj.config_json = dumps(cfg)
    if is_primary and obj.is_active:
        await demote_scenario_primary(db, scenario=scenario, keep_id=obj.id)


@router.post('')
async def create_model_config(
    data: ModelConfigIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    settings = get_settings()
    stored_config = _prepare_stored_config(data.config, settings)

    scenario = data.scenario
    is_primary = bool(data.is_primary)
    if data.model_type == 'llm':
        try:
            scenario, is_primary = validate_llm_scenario_fields(
                scenario=scenario,
                is_primary=is_primary,
                is_active=data.is_active,
                has_api_key=_has_api_key(stored_config),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        scenario = None
        is_primary = False

    obj = ModelConfig(
        model_type=data.model_type,
        scenario=scenario,
        model_name=data.model_name,
        version=data.version,
        api_endpoint=data.api_endpoint,
        config_json=dumps(stored_config),
        is_active=data.is_active,
        is_primary=is_primary if data.model_type == 'llm' else False,
    )
    db.add(obj)
    await db.flush()

    if data.model_type == 'llm':
        await _apply_llm_routing(db, obj=obj, scenario=scenario, is_primary=is_primary)

    await db.commit()
    await db.refresh(obj)
    invalidate_llm_runtime_cache()
    return {'id': obj.id}


@router.get('')
async def list_model_configs(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    settings = get_settings()
    rows = (
        await db.execute(
            select(ModelConfig).order_by(
                ModelConfig.scenario.asc(),
                ModelConfig.is_primary.desc(),
                ModelConfig.model_type.asc(),
                ModelConfig.created_at.desc(),
            )
        )
    ).scalars().all()
    items = [_serialize_row(x, settings) for x in rows]
    await attach_today_stats(db, items)
    return items


@router.get('/active-llm')
async def get_active_llm_runtime(
    scenario: str = DEFAULT_LLM_SCENARIO,
    admin: User = Depends(require_admin),
):
    cfg = await try_get_llm_runtime_config_async(scenario=scenario, force_refresh=True)
    if not cfg:
        return {
            'configured': False,
            'scenario': scenario,
            'message': '请在管理后台为该场景配置并启用大语言模型',
        }
    return {
        'configured': True,
        'scenario': cfg.scenario,
        'is_primary': cfg.is_primary,
        'model_name': cfg.model_name,
        'base_url': cfg.base_url,
        'temperature': cfg.temperature,
        'max_tokens': cfg.max_tokens,
        'thinking_enabled': cfg.thinking_enabled,
        'reasoning_effort': cfg.reasoning_effort,
        'config_id': cfg.config_id,
        'has_api_key': bool(cfg.api_key),
    }


@router.get('/{model_id}/detail')
async def get_model_detail(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    detail = await build_model_detail(db, model_id)
    if not detail:
        raise HTTPException(status_code=404, detail='模型配置不存在')
    settings = get_settings()
    obj = await db.get(ModelConfig, model_id)
    secret = _encryption_secret(settings)
    detail['config'] = sanitize_config_for_response(loads(obj.config_json, {}), secret)
    detail['scenario'] = obj.scenario
    detail['scenario_name'] = serialize_model_config_row(obj, detail['config'])['scenario_name']
    detail['is_primary'] = bool(obj.is_primary)
    return detail


@router.put('/{model_id}')
async def update_model_config(
    model_id: int,
    data: ModelConfigUpdateIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    obj = await db.get(ModelConfig, model_id)
    if not obj:
        raise HTTPException(status_code=404, detail='模型配置不存在')

    settings = get_settings()
    values = data.model_dump(exclude_unset=True)
    if 'config' in values:
        incoming = values.pop('config') or {}
        old_cfg = loads(obj.config_json, {})
        obj.config_json = dumps(_merge_config_payload(old_cfg, incoming, settings))

    for field, value in values.items():
        setattr(obj, field, value)

    if obj.model_type == 'llm':
        merged_cfg = loads(obj.config_json, {})
        try:
            scenario, is_primary = validate_llm_scenario_fields(
                scenario=obj.scenario,
                is_primary=obj.is_primary,
                is_active=obj.is_active,
                has_api_key=_has_api_key(merged_cfg),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _apply_llm_routing(db, obj=obj, scenario=scenario, is_primary=is_primary)
    else:
        obj.scenario = None
        obj.is_primary = False

    await db.commit()
    invalidate_llm_runtime_cache()
    return {'message': 'updated'}
