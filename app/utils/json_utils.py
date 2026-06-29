import json
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
