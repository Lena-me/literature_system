"""管理端 API 响应脱敏：文献名、用户 PII、错误日志中的用户原文。"""

from __future__ import annotations

import re
from typing import Any

_MASK = '****'

# 常见技术异常名（含 Celery / HTTP / DB / 向量库等）
_TECH_EXCEPTION_RE = re.compile(
    r'\b([A-Z][A-Za-z0-9_]*(?:Error|Exception)|'
    r'TimeoutError|OutOfMemoryError|ConnectionRefusedError|'
    r'HTTPException|ValidationError|IntegrityError|OperationalError|'
    r'RedisError|MilvusException|S3Error|MinioException)\b'
)

# Celery 任务常见格式：ExceptionType: message
_CELERY_ERR_RE = re.compile(
    r'^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)):\s*(.*)$',
    re.DOTALL,
)

_TRACE_LINE_RE = re.compile(
    r'^(Traceback|File "|  File "|During handling|\w+(?:Error|Exception):)',
)

_TECH_HINT_RE = re.compile(
    r'^(timeout|connection|memory|cuda|redis|mysql|milvus|minio|celery|socket|ssl|http)',
    re.I,
)

# 业务实体 ID（paper 18 / user_id=3 等）不得出现在管理端
_ENTITY_REF_RE = re.compile(
    r'\b(paper|user|session|report|document|file)\s*#?\s*\d+\b',
    re.I,
)
_ENTITY_KV_RE = re.compile(
    r'\b(paper_id|user_id|session_id|report_id|document_id)\s*[=:]\s*\d+\b',
    re.I,
)

_ENTITY_WORD_ZH = {
    'paper': '文献',
    'user': '用户',
    'session': '会话',
    'report': '报告',
    'document': '文档',
    'file': '文件',
}

_MSG_ZH = {
    'has been deleted': '目标资源已删除',
    'not found': '目标资源不存在',
    'does not exist': '目标资源不存在',
}

# 疑似用户原文：长句、中文段落、无技术关键词
_USER_PROSE_RE = re.compile(r'[\u4e00-\u9fff]{8,}|[a-zA-Z\s,.]{80,}')


def _redact_error_entities(msg: str) -> str:
    if not msg:
        return ''

    def _repl(m: re.Match[str]) -> str:
        key = m.group(1).lower()
        return _ENTITY_WORD_ZH.get(key, '资源')

    text = _ENTITY_REF_RE.sub(_repl, msg)
    text = _ENTITY_KV_RE.sub('', text)
    text = re.sub(r'\s{2,}', ' ', text).strip(' ,;:')
    lowered = text.lower()
    for en, zh in _MSG_ZH.items():
        if en in lowered:
            text = re.sub(re.escape(en), zh, text, flags=re.I)
            break
    return text.strip()


def mask_head_tail(text: str, *, head: int = 3, tail: int = 2, stars: int = 4) -> str:
    """保留头尾遮蔽中间，如 Att****ed.pdf。"""
    if not text:
        return ''
    raw = text.strip()
    if not raw:
        return ''

    ext = ''
    base = raw
    if '.' in raw and not raw.startswith('.'):
        base, ext_part = raw.rsplit('.', 1)
        if ext_part and len(ext_part) <= 8 and re.fullmatch(r'[A-Za-z0-9]+', ext_part):
            ext = f'.{ext_part}'

    n = len(base)
    star_str = '*' * stars

    if n <= head:
        return (base if n <= 1 else base[0] + star_str) + ext
    if n <= head + tail:
        return base[:head] + star_str + ext
    return f'{base[:head]}{star_str}{base[-tail:]}{ext}'


def mask_paper_filename(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    return mask_head_tail(str(value), head=3, tail=2, stars=4)


def mask_paper_title(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    if '.' in text and len(text.split('.')[-1]) <= 8:
        return mask_paper_filename(text)
    return mask_head_tail(text, head=2, tail=2, stars=4)


def mask_username(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    s = str(value).strip()
    if re.fullmatch(r'\d+', s):
        return f'用户{_MASK}'
    n = len(s)
    if n <= 1:
        return '用*'
    if n == 2:
        return s[0] + '·*'
    if n <= 4:
        return s[0] + '··' + s[-1]
    return s[:2] + '··' + s[-1]


def mask_email(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    s = str(value).strip()
    if '@' not in s:
        return mask_username(s)
    local, domain = s.split('@', 1)
    masked_local = mask_username(local) or '***'
    if '.' in domain:
        parts = domain.split('.')
        masked_domain = (parts[0][:1] + '***.' + parts[-1]) if parts[0] else domain
    else:
        masked_domain = domain[:1] + '***' if domain else '***'
    return f'{masked_local}@{masked_domain}'


def mask_phone(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    s = re.sub(r'\s+', '', str(value).strip())
    if len(s) <= 4:
        return '*' * len(s)
    if len(s) <= 7:
        return s[:2] + '***' + s[-1:]
    return s[:3] + '****' + s[-4:]


def mask_display_name(value: str | None) -> str | None:
    """真实姓名等同 username 规则打码。"""
    return mask_username(value)


def _shorten_path_line(line: str) -> str:
    return re.sub(r'File "[^"]*[/\\]([^/\\"]+)"', r'File "\1"', line)


def _extract_technical_message(msg: str) -> str:
    msg = _redact_error_entities((msg or '').strip())
    if not msg:
        return ''
    if _USER_PROSE_RE.search(msg) and not _TECH_EXCEPTION_RE.search(msg):
        return ''
    if len(msg) > 160 and not _TECH_HINT_RE.search(msg[:80]):
        exc = _TECH_EXCEPTION_RE.search(msg)
        return exc.group(1) if exc else ''
    return msg[:160]


def _finalize_error_output(text: str, *, max_len: int) -> str:
    return _redact_error_entities(text)[:max_len]


def sanitize_technical_error_log(raw: str | None, *, max_len: int = 480) -> str | None:
    """
    从 error_log 提取纯技术信息，过滤用户原文段落与过长上下文。
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    celery = _CELERY_ERR_RE.match(text)
    if celery:
        exc_type = celery.group(1)
        tech_msg = _extract_technical_message(celery.group(2))
        if tech_msg:
            out = f'{exc_type}: {tech_msg}'
        else:
            out = exc_type
        return _finalize_error_output(out, max_len=max_len)

    if 'Traceback' in text:
        lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if _TRACE_LINE_RE.match(stripped) or _TECH_EXCEPTION_RE.search(stripped):
                lines.append(_shorten_path_line(stripped)[:220])
            elif _TECH_HINT_RE.match(stripped) and len(stripped) < 120:
                lines.append(stripped[:220])
        if lines:
            return _finalize_error_output('\n'.join(lines[:10]), max_len=max_len)
        found = _TECH_EXCEPTION_RE.findall(text)
        if found:
            return _finalize_error_output(', '.join(dict.fromkeys(found)), max_len=max_len)

    if _USER_PROSE_RE.search(text) and not _TECH_EXCEPTION_RE.search(text):
        found = _TECH_EXCEPTION_RE.findall(text)
        return found[0] if found else 'ProcessingError'

    if len(text) > 120:
        found = _TECH_EXCEPTION_RE.findall(text)
        if found:
            return ', '.join(dict.fromkeys(found))[:max_len]
        if _TECH_HINT_RE.search(text[:80]):
            return text[:120]
        return 'ProcessingError'

    if _TECH_EXCEPTION_RE.search(text) or _TECH_HINT_RE.search(text):
        return _finalize_error_output(text, max_len=max_len)

    return 'ProcessingError'


def sanitize_error_cluster_summary(summary: str | None) -> str:
    """运维总览错误聚类摘要脱敏。"""
    sanitized = sanitize_technical_error_log(summary, max_len=120)
    return sanitized or 'UnknownError'


def mask_user_fields(data: dict[str, Any]) -> dict[str, Any]:
    """就地脱敏用户相关字段（用于 dict 流水线）。"""
    out = dict(data)
    for key, fn in (
        ('username', mask_username),
        ('email', mask_email),
        ('phone', mask_phone),
        ('name', mask_display_name),
    ):
        if key in out and out[key] is not None:
            out[key] = fn(out[key])
    return out
