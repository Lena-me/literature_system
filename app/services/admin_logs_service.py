from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User, VectorDBSnapshot
from app.schemas.admin import AdminAuditLogListOut, AdminAuditLogOut
from app.utils.json_utils import loads


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = f'{text[:-1]}+00:00'
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.strptime(text[:10], '%Y-%m-%d')
        except ValueError:
            return None


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse_operation_content(raw: str | None) -> tuple[str | None, Any | None]:
    if raw is None or raw == '':
        return None, None
    stripped = raw.strip()
    if stripped.startswith(('{', '[')):
        parsed = loads(raw, default=None)
        if isinstance(parsed, (dict, list)):
            return raw, parsed
    return raw, None


_MODULE_LABELS: dict[str, str] = {
    'auth': '账号',
    'papers': '文献',
    'qa': '问答',
    'reports': '报告',
    'admin': '管理',
}

_ACTION_LABELS: dict[str, str] = {
    'login': '登录',
    'login_failed': '登录失败',
    'register': '注册',
    'reset_password': '重置密码',
    'update_profile': '修改资料',
    'upload': '上传',
    'delete': '删除',
    'reparse': '重新解析',
    'ask': '提问',
    'ask_stream': '流式提问',
    'generate': '生成报告',
}


def audit_operation_summary(
    module: str | None,
    operation_type: str | None,
    *,
    content_raw: str | None = None,
    content_json: Any = None,
) -> str:
    """管理端展示用摘要：不暴露文献名、提问内容、文件名等用户隐私。"""
    if content_json is None and content_raw:
        _, content_json = _parse_operation_content(content_raw)

    module_key = (module or '').strip()
    op_key = (operation_type or '').strip()

    if module_key == 'papers':
        if op_key == 'upload':
            if isinstance(content_json, dict):
                size = content_json.get('file_size')
                if isinstance(size, (int, float)) and size > 0:
                    kb = int(size) // 1024
                    return f'上传文献（约 {kb} KB）' if kb > 0 else '上传文献'
            return '上传文献'
        if op_key == 'delete':
            return '删除文献'
        if op_key == 'reparse':
            return '重新解析文献'

    if module_key == 'qa':
        paper_count = 0
        if isinstance(content_json, dict):
            ids = content_json.get('paper_ids')
            if isinstance(ids, list):
                paper_count = len(ids)
        if op_key == 'ask_stream':
            return f'发起流式问答（{paper_count} 篇文献）' if paper_count else '发起流式问答'
        if op_key == 'ask':
            return f'发起问答（{paper_count} 篇文献）' if paper_count else '发起问答'

    if module_key == 'reports':
        if op_key == 'generate':
            return '生成研读报告'
        if op_key == 'delete':
            return '删除报告'

    if module_key == 'auth':
        auth_labels = {
            'login': '登录成功',
            'login_failed': '登录失败',
            'register': '注册账号',
            'reset_password': '重置密码',
            'update_profile': '修改个人资料',
        }
        if op_key in auth_labels:
            return auth_labels[op_key]

    module_label = _MODULE_LABELS.get(module_key, module_key or '操作')
    action_label = _ACTION_LABELS.get(op_key, op_key)
    if action_label and action_label != module_label:
        return f'{module_label} · {action_label}'
    return module_label or action_label or '—'


def _audit_item(log: AuditLog, username: str | None) -> dict:
    content_raw, content_json = _parse_operation_content(log.operation_content)
    item = AdminAuditLogOut(
        username=username,
        module=log.module,
        operation_type=log.operation_type,
        operation_summary=audit_operation_summary(
            log.module,
            log.operation_type,
            content_raw=content_raw,
            content_json=content_json,
        ),
        operation_result=log.operation_result,
        ip_address=log.ip_address,
        risk_flag=log.risk_flag,
        created_at=_iso(log.created_at),
    )
    return item.model_dump()


def _snapshot_item(row: VectorDBSnapshot) -> dict:
    return {
        'id': row.id,
        'total_vectors': int(row.total_vectors or 0),
        'storage_mb': float(row.storage_mb or 0),
        'index_count': int(row.index_count or 0),
        'shard_count': int(row.shard_count or 0),
        'avg_search_latency_ms': float(row.avg_search_latency_ms or 0),
        'p95_search_latency_ms': float(row.p95_search_latency_ms or 0),
        'search_success_rate': float(row.search_success_rate or 0),
        'recall_rate': float(row.recall_rate or 0),
        'health_score': float(row.health_score or 0),
        'recorded_at': _iso(row.created_at),
    }


def _end_user_audit_clause():
    """风控中心只展示终端用户行为；管理员账号的操作仍落库，但不在此列表展示。"""
    return or_(AuditLog.user_id.is_(None), User.role.is_(None), User.role != 'admin')


async def list_audit_logs(
    db: AsyncSession,
    *,
    page: int = 1,
    size: int = 20,
    user_id: int | None = None,
    risk_flag: bool | None = None,
    keyword: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
) -> dict:
    page = max(page, 1)
    size = min(max(size, 1), 100)

    filters = [_end_user_audit_clause()]
    if user_id is not None:
        filters.append(AuditLog.user_id == user_id)
    if risk_flag is True:
        filters.append(AuditLog.risk_flag > 0)
    start_dt = _parse_dt(start_at)
    end_dt = _parse_dt(end_at)
    if start_dt is not None:
        filters.append(AuditLog.created_at >= start_dt)
    if end_dt is not None:
        end_bound = end_dt.replace(hour=23, minute=59, second=59) if end_dt.hour == 0 and end_dt.minute == 0 else end_dt
        filters.append(AuditLog.created_at <= end_bound)
    if keyword and keyword.strip():
        kw = f'%{keyword.strip()}%'
        filters.append(
            or_(
                AuditLog.operation_content.like(kw),
                AuditLog.operation_type.like(kw),
                AuditLog.module.like(kw),
                User.username.like(kw),
            )
        )

    count_stmt = select(func.count()).select_from(AuditLog).outerjoin(User, AuditLog.user_id == User.id)
    data_stmt = select(AuditLog, User.username).outerjoin(User, AuditLog.user_id == User.id)
    for clause in filters:
        count_stmt = count_stmt.where(clause)
        data_stmt = data_stmt.where(clause)

    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    rows = (
        await db.execute(
            data_stmt.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()

    return AdminAuditLogListOut(
        items=[_audit_item(log, username) for log, username in rows],
        total=total,
        page=page,
        size=size,
    ).model_dump()


async def list_vector_snapshots(
    db: AsyncSession,
    *,
    days: int = 7,
    limit: int = 168,
) -> dict:
    days = min(max(days, 1), 90)
    limit = min(max(limit, 1), 500)
    since = datetime.now() - timedelta(days=days)

    rows = (
        await db.execute(
            select(VectorDBSnapshot)
            .where(VectorDBSnapshot.created_at >= since)
            .order_by(VectorDBSnapshot.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    items = [_snapshot_item(x) for x in reversed(rows)]
    latest = items[-1] if items else None
    series = [int(x['total_vectors']) for x in items]

    return {
        'items': items,
        'latest': latest,
        'series': series,
        'days': days,
    }
