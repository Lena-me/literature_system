from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field

class APIResponse(BaseModel):
    code: int = 0
    message: str = 'success'
    data: Any = None

class TokenOut(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    user: dict[str, Any]

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=18)
    confirm_password: str = Field(min_length=6, max_length=18)
    email: str | None = None
    phone: str
    code: str = Field(min_length=4, max_length=8)

class LoginIn(BaseModel):
    phone: str
    password: str

class VerificationCodeIn(BaseModel):
    phone: str
    purpose: Literal['register', 'reset_password'] = 'register'

class ResetPasswordIn(BaseModel):
    phone: str
    code: str = Field(min_length=4, max_length=8)
    password: str = Field(min_length=6, max_length=18)
    confirm_password: str = Field(min_length=6, max_length=18)

class UserOut(BaseModel):
    id: int
    username: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    role: str
    status: str
    paper_upload_count: int = 0
    report_generate_count: int = 0
    created_at: datetime
    model_config = {'from_attributes': True}

class UserUpdateIn(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    status: str | None = None
    role: str | None = None
    quota: dict[str, Any] | None = None

class CategoryIn(BaseModel):
    name: str
    parent_id: int | None = None

class PaperOut(BaseModel):
    id: int
    original_filename: str
    file_size: int
    upload_time: datetime
    parse_status: str
    title: str | None = None
    authors: Any = None
    keywords: Any = None
    subject_labels: Any = None
    notes: str | None = None
    category_id: int | None = None
    doi: str | None = None
    publication_year: int | None = None
    journal_conf: str | None = None
    model_config = {'from_attributes': True}

class PaperUpdateIn(BaseModel):
    title: str | None = None
    authors: list[str] | None = None
    keywords: list[str] | None = None
    subject_labels: list[str] | None = None
    notes: str | None = None
    category_id: int | None = None
    doi: str | None = None
    publication_year: int | None = None
    journal_conf: str | None = None

class QAAskIn(BaseModel):
    question: str = Field(min_length=1)
    paper_ids: list[int] | None = None
    session_id: int | None = None
    top_k: int | None = None

class SessionCreateIn(BaseModel):
    title: str | None = None
    paper_ids: list[int] | None = None

class SessionUpdateIn(BaseModel):
    title: str | None = None
    add_paper_ids: list[int] | None = None
    remove_paper_ids: list[int] | None = None

class ReportCreateIn(BaseModel):
    paper_id: int
    modules: list[str] | None = None
    title: str | None = None

class CompareIn(BaseModel):
    paper_ids: list[int] = Field(min_length=2, max_length=5)
    dimensions: list[str] | None = None
    name: str | None = None

class GraphCreateIn(BaseModel):
    paper_ids: list[int] = Field(min_length=1, max_length=5)
    name: str | None = None

class ReproGuideCreateIn(BaseModel):
    paper_id: int

class LearningRecordIn(BaseModel):
    paper_id: int | None = None
    event_type: str
    event_data: dict[str, Any] | None = None

class ModelConfigIn(BaseModel):
    model_type: Literal['parse', 'vector', 'reranker', 'llm']
    model_name: str
    version: str | None = None
    api_endpoint: str | None = None
    config: dict[str, Any] | None = None
    is_active: bool = True

class SchedulerConfigIn(BaseModel):
    max_concurrent_tasks: int = 4
    per_user_concurrent: int = 2
    timeout_seconds: int = 300
    alert_rules: dict[str, Any] | None = None
    backup_engine_config: dict[str, Any] | None = None

class EvidenceMatrixIn(BaseModel):
    paper_ids: list[int] = Field(min_length=1, max_length=10)
    question: str | None = None

class ResearchRadarIn(BaseModel):
    paper_ids: list[int] = Field(min_length=1, max_length=10)

class ChunkUploadInitIn(BaseModel):
    filename: str
    total_size: int = Field(gt=0)
    total_chunks: int = Field(gt=0)
    chunk_size: int = Field(gt=0)

class ChunkUploadCompleteIn(BaseModel):
    upload_id: str

class TaskPriorityIn(BaseModel):
    priority: int = Field(ge=0, le=9)

class TaskBatchRetryIn(BaseModel):
    task_ids: list[int] = Field(min_length=1, max_length=100)

class VectorRestoreIn(BaseModel):
    backup_id: int

class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    name: str | None = None
    email: str | None = None
    phone: str
    role: Literal['researcher', 'admin'] = 'researcher'
    status: Literal['active', 'disabled'] = 'active'
    quota: dict[str, Any] | None = None

