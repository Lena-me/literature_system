"""管理端 API 响应 Schema：序列化阶段强制脱敏。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.utils.admin_privacy import (
    mask_email,
    mask_paper_filename,
    mask_paper_title,
    mask_phone,
)


def _iso_dt(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class AdminUserOut(BaseModel):
    id: int
    username: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    role: str
    status: str
    paper_upload_count: int = 0
    report_generate_count: int = 0
    quota: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    last_login_at: str | None = None
    last_login_ip: str | None = None

    @field_validator('email', mode='before')
    @classmethod
    def _v_email(cls, v: Any) -> Any:
        return mask_email(v) if v else v

    @field_validator('phone', mode='before')
    @classmethod
    def _v_phone(cls, v: Any) -> Any:
        return mask_phone(v) if v else v

    @field_validator('created_at', 'last_login_at', mode='before')
    @classmethod
    def _v_dt(cls, v: Any) -> Any:
        return _iso_dt(v)


class AdminUserDetailOut(BaseModel):
    user: AdminUserOut
    audit_logs: list['AdminAuditLogOut'] = Field(default_factory=list)


class AdminAuditLogOut(BaseModel):
    username: str | None = None
    module: str | None = None
    operation_type: str | None = None
    operation_summary: str | None = None
    operation_result: str | None = None
    ip_address: str | None = None
    risk_flag: int = 0
    created_at: str | None = None

    @field_validator('created_at', mode='before')
    @classmethod
    def _v_dt(cls, v: Any) -> Any:
        return _iso_dt(v)


class AdminAuditLogListOut(BaseModel):
    items: list[AdminAuditLogOut]
    total: int
    page: int
    size: int


class AdminTaskOut(BaseModel):
    id: int
    username: str | None = None
    paper_label: str | None = None
    task_type: str
    status: str
    priority: int = 5
    queue_position: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    duration_ms: int | None = None
    retry_count: int = 0
    error_log: str | None = None
    created_at: str | None = None

    @field_validator('paper_label', mode='before')
    @classmethod
    def _v_paper_label(cls, v: Any) -> Any:
        if v is None or not str(v).strip():
            return None
        text = str(v).strip()
        if '.' in text and not text.startswith('.'):
            return mask_paper_filename(text)
        return mask_paper_title(text)

    @field_validator('start_time', 'end_time', 'created_at', mode='before')
    @classmethod
    def _v_dt(cls, v: Any) -> Any:
        return _iso_dt(v)


class AdminTaskStatsOut(BaseModel):
    total: int = 0
    running: int = 0
    failed: int = 0
    queued: int = 0
    completed: int = 0
    cancelled: int = 0


class AdminTaskListOut(BaseModel):
    items: list[AdminTaskOut]
    total: int
    page: int
    page_size: int
    stats: AdminTaskStatsOut = Field(default_factory=AdminTaskStatsOut)


class AdminTopUserOut(BaseModel):
    id: int
    username: str | None = None
    name: str | None = None
    tokens: int = 0
    uploads: int = 0
    qa_calls: int = 0
    consumption: int = 0
    consumption_pct: float = 0.0


class AdminErrorClusterOut(BaseModel):
    summary: str
    count: int


class AdminOverviewOut(BaseModel):
    health: dict[str, Any]
    cards: dict[str, Any]
    vector_snapshots: dict[str, Any]
    trends: dict[str, Any]
    error_clusters: list[AdminErrorClusterOut] = Field(default_factory=list)
    error_clusters_meta: dict[str, Any] = Field(default_factory=dict)
    top_users: list[AdminTopUserOut] = Field(default_factory=list)
    top_users_meta: dict[str, Any] = Field(default_factory=dict)


class AdminPaperRefOut(BaseModel):
    """若管理端需引用文献，仅返回遮蔽字段。"""

    id: int
    title: str | None = None
    original_filename: str | None = None

    @field_validator('title', mode='before')
    @classmethod
    def _v_title(cls, v: Any) -> Any:
        return mask_paper_title(v) if v else v

    @field_validator('original_filename', mode='before')
    @classmethod
    def _v_filename(cls, v: Any) -> Any:
        return mask_paper_filename(v) if v else v


class AdminFailureReasonOut(BaseModel):
    reason: str
    count: int
