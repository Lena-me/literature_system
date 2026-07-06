from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.dependencies import require_admin
from app.db.mysql import get_db
from app.integrations.llm.runtime_config import get_llm_runtime_config_async, invalidate_llm_runtime_cache
from app.models import ModelConfig, User
from app.schemas import ModelConfigIn
from app.utils.json_utils import dumps, loads
router = APIRouter(prefix='/model-configs', tags=['模型管理'])

class ModelConfigUpdateIn(BaseModel):
    model_type: Literal['parse', 'vector', 'reranker', 'llm'] | None = None
    model_name: str | None = None
    version: str | None = None
    api_endpoint: str | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


async def _ensure_single_active_llm(db: AsyncSession, keep_id: int) -> None:
    await db.execute(
        update(ModelConfig)
        .where(ModelConfig.model_type == 'llm', ModelConfig.id != keep_id, ModelConfig.is_active.is_(True))
        .values(is_active=False)
    )


@router.post('')
async def create_model_config(data: ModelConfigIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    obj = ModelConfig(model_type=data.model_type, model_name=data.model_name, version=data.version, api_endpoint=data.api_endpoint, config_json=dumps(data.config or {}), is_active=data.is_active)
    db.add(obj)
    await db.flush()
    if data.model_type == 'llm' and data.is_active:
        await _ensure_single_active_llm(db, obj.id)
    await db.commit()
    await db.refresh(obj)
    invalidate_llm_runtime_cache()
    return {'id': obj.id}

@router.get('')
async def list_model_configs(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    rows = (await db.execute(select(ModelConfig).order_by(ModelConfig.model_type.asc(), ModelConfig.created_at.desc()))).scalars().all()
    return [{'id': x.id, 'model_type': x.model_type, 'model_name': x.model_name, 'version': x.version, 'api_endpoint': x.api_endpoint, 'config': loads(x.config_json,{}), 'is_active': x.is_active} for x in rows]


@router.get('/active-llm')
async def get_active_llm_runtime(admin: User = Depends(require_admin)):
    cfg = await get_llm_runtime_config_async(force_refresh=True)
    return {
        'model_name': cfg.model_name,
        'base_url': cfg.base_url,
        'temperature': cfg.temperature,
        'max_tokens': cfg.max_tokens,
        'source': cfg.source,
        'config_id': cfg.config_id,
        'env_fallback_model': get_settings().llm_model,
    }

@router.put('/{model_id}')
async def update_model_config(model_id: int, data: ModelConfigUpdateIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    obj = await db.get(ModelConfig, model_id)
    if not obj:
        raise HTTPException(status_code=404, detail='模型配置不存在')

    values = data.model_dump(exclude_unset=True)
    if 'config' in values:
        obj.config_json = dumps(values.pop('config') or {})

    for field, value in values.items():
        setattr(obj, field, value)

    if obj.model_type == 'llm' and obj.is_active:
        await _ensure_single_active_llm(db, obj.id)

    await db.commit()
    invalidate_llm_runtime_cache()
    return {'message': 'updated'}
