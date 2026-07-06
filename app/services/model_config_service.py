from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModelConfig
from app.services.model_scenarios import DEFAULT_LLM_SCENARIO, scenario_name, validate_scenario
from app.utils.json_utils import dumps, loads


async def demote_scenario_primary(
    db: AsyncSession,
    *,
    scenario: str,
    keep_id: int,
) -> None:
    """同场景下已有主干模型时，自动降级为备用。"""
    rows = (
        await db.execute(
            select(ModelConfig).where(
                ModelConfig.model_type == 'llm',
                ModelConfig.scenario == scenario,
                ModelConfig.is_active.is_(True),
                ModelConfig.is_primary.is_(True),
                ModelConfig.id != keep_id,
            )
        )
    ).scalars().all()
    for row in rows:
        row.is_primary = False
        cfg = loads(row.config_json, {})
        cfg['route_role'] = 'fallback'
        row.config_json = dumps(cfg)


def serialize_model_config_row(x: ModelConfig, config: dict) -> dict:
    return {
        'id': x.id,
        'model_type': x.model_type,
        'scenario': x.scenario,
        'scenario_name': scenario_name(x.scenario),
        'model_name': x.model_name,
        'version': x.version,
        'api_endpoint': x.api_endpoint,
        'config': config,
        'is_active': x.is_active,
        'is_primary': bool(x.is_primary),
    }


def validate_llm_scenario_fields(*, scenario: str | None, is_primary: bool | None, is_active: bool, has_api_key: bool) -> tuple[str, bool]:
    scenario_value = validate_scenario(scenario, required=True)
    primary_value = bool(is_primary)
    if is_active and not has_api_key:
        raise ValueError('启用 LLM 必须在管理后台填写 API Key')
    return scenario_value, primary_value


def default_scenario_for_type(model_type: str) -> str | None:
    if model_type == 'llm':
        return DEFAULT_LLM_SCENARIO
    return None
