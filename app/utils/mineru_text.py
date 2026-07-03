from __future__ import annotations

import json
import re

from app.utils.text_utils import normalize_text


def extract_text_from_mineru_obj(value) -> str:
    """递归从 MinerU v2 嵌套结构中提取可读文本。"""
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [extract_text_from_mineru_obj(item) for item in value]
        return normalize_text('\n'.join(part for part in parts if part))
    if isinstance(value, dict):
        if value.get('list_items'):
            lines: list[str] = []
            for item in value.get('list_items') or []:
                if not isinstance(item, dict):
                    continue
                line = extract_text_from_mineru_obj(
                    item.get('item_content') or item.get('content') or item
                )
                if line:
                    lines.append(line)
            return normalize_text('\n'.join(lines))
        if 'item_content' in value:
            return extract_text_from_mineru_obj(value.get('item_content'))
        for key in (
            'paragraph_content',
            'title_content',
            'math_content',
            'text',
            'content',
            'html',
            'caption',
        ):
            if key in value and value.get(key) is not None:
                extracted = extract_text_from_mineru_obj(value.get(key))
                if extracted:
                    return extracted
        return ''
    return str(value).strip()


def unwrap_mineru_json_text(text: str) -> str:
    """将误入库的 MinerU JSON 字符串还原为正文。"""
    raw = (text or '').strip()
    if not raw:
        return raw
    if raw.startswith('{') or raw.startswith('['):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        extracted = extract_text_from_mineru_obj(parsed)
        if extracted:
            return extracted
    if '"item_content"' in raw or '"item_type"' in raw:
        try:
            parsed = json.loads(raw)
            extracted = extract_text_from_mineru_obj(parsed)
            if extracted:
                return extracted
        except json.JSONDecodeError:
            pass
    return raw


def looks_like_mineru_json_blob(text: str) -> bool:
    raw = (text or '').strip()
    if not raw.startswith('{'):
        return False
    return '"item_content"' in raw or '"item_type"' in raw or '"paragraph_content"' in raw
