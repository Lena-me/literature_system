from __future__ import annotations

import re

_DEFAULT_SESSION_TITLES = {
    '新会话',
    '新对话',
    '新建会话',
    '未命名',
    'new chat',
    'new session',
    '新研究',
}

_TITLE_PREFIX_RE = re.compile(r'^(?:标题|名称|title)\s*[:：]\s*', re.I)
_MARKDOWN_FENCE_RE = re.compile(r'^```(?:\w+)?\s*|\s*```$')


def is_default_session_title(title: str | None) -> bool:
    if not title or not title.strip():
        return True
    return title.strip().lower() in {t.lower() for t in _DEFAULT_SESSION_TITLES}


def fallback_session_title(first_message: str, *, max_len: int = 12) -> str:
    text = re.sub(r'\s+', ' ', (first_message or '').strip())
    text = re.sub(r'[？?！!。，,.；;：:]+$', '', text).strip()
    if not text:
        return '新对话'
    return text[:max_len]


def sanitize_session_title(raw: str | None, *, fallback: str = '', max_len: int = 20) -> str:
    text = (raw or '').strip()
    if not text:
        return fallback[:max_len]

    text = _MARKDOWN_FENCE_RE.sub('', text).strip()
    text = text.strip('`"\'“”‘’ ')
    text = _TITLE_PREFIX_RE.sub('', text).strip()

    if '\n' in text:
        lines = [ln.strip('`"\'“”‘’ ') for ln in text.splitlines() if ln.strip()]
        picked = ''
        for candidate in reversed(lines):
            candidate = _TITLE_PREFIX_RE.sub('', candidate).strip('`"\'“”‘’ ')
            if 2 <= len(candidate) <= max_len:
                picked = candidate
                break
        if not picked and lines:
            picked = _TITLE_PREFIX_RE.sub('', lines[-1]).strip('`"\'“”‘’ ')
        text = picked or text.splitlines()[0].strip()

    text = re.sub(r'\s+', '', text)
    if len(text) > max_len:
        text = text[:max_len]
    return text or fallback[:max_len]
