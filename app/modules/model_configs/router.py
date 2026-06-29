from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import require_admin
from app.db.mysql import get_db
from app.models import ModelConfig, User
from app.schemas import ModelConfigIn
from app.utils.json_utils import dumps, loads
router = APIRouter(prefix='/model-configs', tags=['模型管理'])

@router.post('')
async def create_model_config(data: ModelConfigIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    obj = ModelConfig(model_type=data.model_type, model_name=data.model_name, version=data.version, api_endpoint=data.api_endpoint, config_json=dumps(data.config or {}), is_active=data.is_active)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return {'id': obj.id}

@router.get('')
async def list_model_configs(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    rows = (await db.execute(select(ModelConfig).order_by(ModelConfig.model_type.asc(), ModelConfig.created_at.desc()))).scalars().all()
    return [{'id': x.id, 'model_type': x.model_type, 'model_name': x.model_name, 'version': x.version, 'api_endpoint': x.api_endpoint, 'config': loads(x.config_json,{}), 'is_active': x.is_active} for x in rows]
