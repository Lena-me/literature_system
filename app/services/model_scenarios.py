from __future__ import annotations

from typing import Literal

ScenarioId = Literal['parse', 'qa', 'report', 'tagging']

MODEL_SCENARIOS: list[dict[str, str]] = [
    {'id': 'parse', 'name': '文献结构化提取'},
    {'id': 'qa', 'name': '实时知识问答'},
    {'id': 'report', 'name': '科研综述生成'},
    {'id': 'tagging', 'name': '智能标签分类'},
]

SCENARIO_IDS = {item['id'] for item in MODEL_SCENARIOS}
SCENARIO_NAME_MAP = {item['id']: item['name'] for item in MODEL_SCENARIOS}

DEFAULT_LLM_SCENARIO = 'qa'
DEFAULT_NON_LLM_SCENARIO = 'default'


def scenario_name(scenario: str | None) -> str | None:
    if not scenario:
        return None
    return SCENARIO_NAME_MAP.get(scenario, scenario)


def validate_scenario(scenario: str | None, *, required: bool = False) -> str | None:
    if scenario is None or str(scenario).strip() == '':
        if required:
            raise ValueError('scenario 不能为空')
        return None
    text = str(scenario).strip()
    if text not in SCENARIO_IDS:
        raise ValueError(f'不支持的业务场景: {text}')
    return text
