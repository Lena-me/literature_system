from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

from app.utils.json_utils import coerce_str_list

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
    code: str = Field(min_length=6, max_length=6)

class LoginIn(BaseModel):
    phone: str
    password: str

class SendCodeIn(BaseModel):
    phone: str
    purpose: Literal['register', 'reset_password'] = 'register'

class VerifyCodeIn(BaseModel):
    phone: str
    purpose: Literal['register', 'reset_password'] = 'register'
    code: str = Field(min_length=6, max_length=6)

VerificationCodeIn = VerifyCodeIn

class ResetPasswordIn(BaseModel):
    token: str
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
    avatar_url: str | None = None
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
    authors: list[str] | None = None
    keywords: list[str] | None = None
    subject_labels: list[str] | None = None
    notes: str | None = None
    category_id: int | None = None
    doi: str | None = None
    publication_year: int | None = None
    journal_conf: str | None = None
    model_config = {'from_attributes': True}

    @field_validator('authors', 'keywords', 'subject_labels', mode='before')
    @classmethod
    def _parse_list_fields(cls, value: Any) -> list[str] | None:
        return coerce_str_list(value)

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

    @field_validator('authors', 'keywords', 'subject_labels', mode='before')
    @classmethod
    def _coerce_list_fields(cls, value: Any) -> list[str] | None:
        return coerce_str_list(value)

class QAAskIn(BaseModel):
    question: str = Field(min_length=1)
    paper_ids: list[int] | None = None
    session_id: int | None = None
    top_k: int | None = None
    regenerate: bool = False

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

class CompareNameIn(BaseModel):
    paper_ids: list[int] = Field(min_length=2, max_length=5)
    dimensions: list[str] | None = None

class GraphCreateIn(BaseModel):
    paper_ids: list[int] = Field(min_length=1, max_length=5)
    name: str | None = None
    domain_id: int | None = None

class DomainCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    icon: str = 'folder'
    parent_domain_id: int | None = None

class DomainUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None

class DomainOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    icon: str
    parent_domain_id: int | None = None
    graph_count: int = 0
    paper_count: int = 0
    created_at: datetime
    updated_at: datetime
    model_config = {'from_attributes': True}

class GraphSummaryOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    model_config = {'from_attributes': True}

class DomainOverviewOut(BaseModel):
    domain: DomainOut
    graphs: list[GraphSummaryOut] = []

class DomainSuggestIn(BaseModel):
    paper_ids: list[int] = Field(min_length=1, max_length=5)

class DomainSuggestItem(BaseModel):
    domain_id: int | None = None  # None 表示建议新建
    domain_name: str
    match_type: str  # 'existing' | 'new'
    reason: str
    paper_count_in_domain: int = 0

class DomainSuggestOut(BaseModel):
    suggestions: list[DomainSuggestItem] = []

# ==================== 实体融合 ====================

class MergeSuggestionItem(BaseModel):
    node_a: dict
    node_b: dict
    similarity: float

class MergeSuggestionOut(BaseModel):
    suggestions: list[MergeSuggestionItem] = []

class MergeRequestIn(BaseModel):
    source_node_id: int
    target_node_id: int

class MergeResultOut(BaseModel):
    merged_edges: int
    deleted_duplicates: int
    message: str = '合并完成'

# ==================== 知识推荐 ====================

class RecommendationItem(BaseModel):
    concept: str
    entity_type: str = 'concept'
    reason: str = ''
    source: str = 'relation'  # relation / llm
    node_id: int | None = None
    score: float | None = None
    bridge_nodes: list[str] = []

class RecommendationOut(BaseModel):
    domain_id: int
    domain_name: str
    recommendations: list[RecommendationItem] = []
    source: str = 'hybrid'

class ExploreRequestIn(BaseModel):
    concept: str
    source: str = 'relation'

class ExploreResultOut(BaseModel):
    message: str = '已记录探索'

class CoverageInfo(BaseModel):
    coverage_rate: float = 0.0
    covered_count: int = 0
    suggested_count: int = 0
    core_concepts: list[str] = []
    missing_concepts: list[str] = []

class OverviewOutV2(DomainOverviewOut):
    coverage: CoverageInfo | None = None
    recommendation_count: int = 0

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
    scenario: Literal['parse', 'qa', 'report', 'tagging', 'monthly_report'] | None = None
    is_primary: bool = False

class SchedulerConfigIn(BaseModel):
    max_concurrent_tasks: int = 4
    per_user_concurrent: int = 2
    timeout_seconds: int = 300
    alert_rules: dict[str, Any] | None = None
    backup_engine_config: dict[str, Any] | None = None

class EvidenceMatrixIn(BaseModel):
    paper_ids: list[int] = Field(min_length=1, max_length=10)
    question: str | None = None
    dimensions: list[str] | None = None

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

TaskBatchCancelIn = TaskBatchRetryIn

class SystemPauseIn(BaseModel):
    paused: bool

class VectorRestoreIn(BaseModel):
    backup_id: int

class HighlightRectIn(BaseModel):
    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    width: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)


class PaperNoteCreateIn(BaseModel):
    paper_id: int
    page_number: int = Field(ge=1)
    bbox: list[HighlightRectIn] = Field(min_length=1)
    selected_text: str = Field(min_length=1, max_length=8000)
    note_content: str | None = Field(default=None, max_length=8000)
    highlight_color: str = Field(default='#FFEB3B', max_length=20)


class PaperNoteUpdateIn(BaseModel):
    note_content: str | None = Field(default=None, max_length=8000)
    highlight_color: str | None = Field(default=None, max_length=20)


class FormulaExtractIn(BaseModel):
    image_base64: str = Field(min_length=32, max_length=8_000_000)


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    name: str | None = None
    email: str | None = None
    phone: str
    role: Literal['researcher', 'admin'] = 'researcher'
    status: Literal['active', 'disabled'] = 'active'
    quota: dict[str, Any] | None = None

