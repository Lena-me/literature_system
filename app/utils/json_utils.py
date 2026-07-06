import json
import re
from typing import Any

def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)

def loads(data: str | None, default: Any = None) -> Any:
    if data is None or data == '':
        return default
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return default


def coerce_str_list(value: Any) -> list[str] | None:
    """将 JSON 字符串、逗号分隔文本或 list 统一为字符串列表。"""
    if value is None:
        return None
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        parsed = loads(text, default=None)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
        return [s.strip() for s in re.split(r'[,;，；]', text) if s.strip()]
    return None
