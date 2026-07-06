from __future__ import annotations
from datetime import datetime, date, timezone, timedelta
from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Boolean
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

BEIJING_TZ = timezone(timedelta(hours=8))

def utcnow() -> datetime:
    return datetime.now(BEIJING_TZ)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default='researcher', index=True)
    status: Mapped[str] = mapped_column(String(20), default='active', index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_ip: Mapped[str | None] = mapped_column(String(45))
    paper_upload_count: Mapped[int] = mapped_column(Integer, default=0)
    report_generate_count: Mapped[int] = mapped_column(Integer, default=0)
    quota_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), index=True)
    operation_type: Mapped[str] = mapped_column(String(50), index=True)
    operation_content: Mapped[str | None] = mapped_column(Text)
    operation_result: Mapped[str] = mapped_column(String(20), default='success')
    ip_address: Mapped[str | None] = mapped_column(String(45))
    risk_flag: Mapped[int] = mapped_column(Integer, default=0)
    module: Mapped[str] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class Category(Base):
    __tablename__ = 'categories'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey('categories.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Paper(Base):
    __tablename__ = 'papers'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(500))
    object_key: Mapped[str] = mapped_column(String(500), index=True)
    upload_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    parse_status: Mapped[str] = mapped_column(String(30), default='uploaded', index=True)
    title: Mapped[str | None] = mapped_column(String(500), index=True)
    authors: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[str | None] = mapped_column(Text)
    subject_labels: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey('categories.id'))
    doi: Mapped[str | None] = mapped_column(String(100))
    publication_year: Mapped[int | None] = mapped_column(Integer)
    journal_conf: Mapped[str | None] = mapped_column(String(300))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class ContentItem(Base):
    __tablename__ = 'content_items'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id'), index=True)
    item_type: Mapped[str] = mapped_column(String(40), index=True)
    level: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(mysql.LONGTEXT)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey('content_items.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class FiguresTable(Base):
    __tablename__ = 'figures_tables'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id'), index=True)
    type: Mapped[str] = mapped_column(String(20), index=True)
    caption: Mapped[str | None] = mapped_column(mysql.LONGTEXT)
    page_number: Mapped[int | None] = mapped_column(Integer)
    image_path: Mapped[str | None] = mapped_column(String(500))
    extracted_text: Mapped[str | None] = mapped_column(mysql.LONGTEXT)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class PaperExtractedInfo(Base):
    __tablename__ = 'paper_extracted_info'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id'), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(500))
    authors: Mapped[str | None] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[str | None] = mapped_column(Text)
    research_question: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(Text)
    experiment_data: Mapped[str | None] = mapped_column(Text)
    main_results: Mapped[str | None] = mapped_column(Text)
    innovations: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)
    future_work: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class ParseTask(Base):
    __tablename__ = 'parse_tasks'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    task_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(30), default='queued', index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    queue_position: Mapped[int | None] = mapped_column(Integer)
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_log: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class TextChunk(Base):
    __tablename__ = 'text_chunks'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id'), index=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey('content_items.id'))
    chunk_text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    start_position: Mapped[int] = mapped_column(Integer, default=0)
    end_position: Mapped[int] = mapped_column(Integer, default=0)
    chunk_size: Mapped[int] = mapped_column(Integer, default=0)
    overlap_length: Mapped[int] = mapped_column(Integer, default=0)
    vector_dim: Mapped[int] = mapped_column(Integer, default=1024)
    vectorization_status: Mapped[str] = mapped_column(String(30), default='pending')
    embedding_model_id: Mapped[int | None] = mapped_column(ForeignKey('model_configs.id'))
    vector_id_in_vdb: Mapped[str | None] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class ModelConfig(Base):
    __tablename__ = 'model_configs'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_type: Mapped[str] = mapped_column(String(30), index=True)
    scenario: Mapped[str | None] = mapped_column(String(30), index=True)
    model_name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str | None] = mapped_column(String(50))
    api_endpoint: Mapped[str | None] = mapped_column(String(255))
    config_json: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class ModelCallStat(Base):
    __tablename__ = 'model_call_stats'
    __table_args__ = (UniqueConstraint('model_id', 'date', name='uq_model_stat_date'),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(ForeignKey('model_configs.id'), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    total_calls: Mapped[int] = mapped_column(BigInteger, default=0)
    success_count: Mapped[int] = mapped_column(BigInteger, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    avg_latency_ms: Mapped[float] = mapped_column(Float, default=0)
    p95_latency_ms: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class KnowledgeDomain(Base):
    __tablename__ = 'knowledge_domains'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str] = mapped_column(String(50), default='folder')
    parent_domain_id: Mapped[int | None] = mapped_column(ForeignKey('knowledge_domains.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class KnowledgeGraph(Base):
    __tablename__ = 'knowledge_graphs'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    domain_id: Mapped[int | None] = mapped_column(ForeignKey('knowledge_domains.id'), index=True)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey('papers.id'), index=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class KnowledgeGraphPaper(Base):
    __tablename__ = 'knowledge_graph_papers'
    __table_args__ = (UniqueConstraint('graph_id', 'paper_id', name='uq_graph_paper'),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    graph_id: Mapped[int] = mapped_column(ForeignKey('knowledge_graphs.id'), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id'), index=True)

class GraphNode(Base):
    __tablename__ = 'graph_nodes'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    graph_id: Mapped[int] = mapped_column(ForeignKey('knowledge_graphs.id'), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(300))
    properties: Mapped[str | None] = mapped_column(Text)
    embedding_vector: Mapped[str | None] = mapped_column(Text)  # JSON: BGE向量，用于实体对齐
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class GraphEdge(Base):
    __tablename__ = 'graph_edges'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    graph_id: Mapped[int] = mapped_column(ForeignKey('knowledge_graphs.id'), index=True)
    source_node_id: Mapped[int] = mapped_column(ForeignKey('graph_nodes.id'), index=True)
    target_node_id: Mapped[int] = mapped_column(ForeignKey('graph_nodes.id'), index=True)
    relation_type: Mapped[str] = mapped_column(String(50), index=True)
    properties: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class QASession(Base):
    __tablename__ = 'qa_sessions'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(200), default='新对话')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class QAMessage(Base):
    __tablename__ = 'qa_messages'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey('qa_sessions.id'), index=True)
    role: Mapped[str] = mapped_column(String(20), index=True)
    content: Mapped[str] = mapped_column(Text)
    reasoning_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_artifacts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    external_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True, default=utcnow)

class QAMessageSource(Base):
    __tablename__ = 'qa_message_sources'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey('qa_messages.id'), index=True)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey('text_chunks.id'), index=True)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey('papers.id'), index=True)
    section_title: Mapped[str | None] = mapped_column(String(300))
    page_number: Mapped[int | None] = mapped_column(Integer)
    snippet: Mapped[str | None] = mapped_column(String(1000))
    similarity_score: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class QASessionPaper(Base):
    __tablename__ = 'qa_session_papers'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey('qa_sessions.id'), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Report(Base):
    __tablename__ = 'reports'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id'), index=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class ComparisonResult(Base):
    # 对齐上传的 literature_system.sql：表名为 comparison_analyses，字段名为 literature_ids/result。
    # 代码层继续保留 paper_ids/result_json 属性，避免前后端接口改动。
    __tablename__ = 'comparison_analyses'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    paper_ids: Mapped[str] = mapped_column('literature_ids', Text)
    result_json: Mapped[str | None] = mapped_column('result', Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class ReproducibilityGuide(Base):
    __tablename__ = 'reproducibility_guides'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    guide_content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class LearningRecord(Base):
    __tablename__ = 'learning_records'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey('papers.id'), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    event_data: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class LearningDuration(Base):
    __tablename__ = 'learning_duration'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    record_date: Mapped[date] = mapped_column(Date, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    week_of_year: Mapped[str] = mapped_column(String(10), index=True)
    month_of_year: Mapped[str] = mapped_column(String(7), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class OperationStat(Base):
    __tablename__ = 'operation_stats'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stat_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    registered_users: Mapped[int] = mapped_column(Integer, default=0)
    dau: Mapped[int] = mapped_column(Integer, default=0)
    total_uploaded: Mapped[int] = mapped_column(Integer, default=0)
    total_parsed: Mapped[int] = mapped_column(Integer, default=0)
    total_qa_calls: Mapped[int] = mapped_column(Integer, default=0)
    vector_db_total: Mapped[int] = mapped_column(BigInteger, default=0)
    feature_usage_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class SystemLog(Base):
    __tablename__ = 'system_logs'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(10), index=True)
    service_name: Mapped[str] = mapped_column(String(100), index=True)
    message: Mapped[str] = mapped_column(Text)
    stack_trace: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    exception_type: Mapped[str | None] = mapped_column(String(200))
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class TaskSchedulerConfig(Base):
    __tablename__ = 'task_scheduler_config'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer, default=4)
    per_user_concurrent: Mapped[int] = mapped_column(Integer, default=2)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    alert_rules: Mapped[str | None] = mapped_column(Text)
    backup_engine_config: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class VectorBackup(Base):
    __tablename__ = 'vector_backups'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    backup_type: Mapped[str] = mapped_column(String(20), default='manual')
    backup_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    file_size_mb: Mapped[float] = mapped_column(Float, default=0)
    file_location: Mapped[str] = mapped_column(String(500))
    retention_count: Mapped[int] = mapped_column(Integer, default=7)
    status: Mapped[str] = mapped_column(String(20), default='completed')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class VectorRestoreTask(Base):
    __tablename__ = 'vector_restore_tasks'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    backup_id: Mapped[int] = mapped_column(ForeignKey('vector_backups.id'), index=True)
    restore_progress: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default='in_progress')
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_log: Mapped[str | None] = mapped_column(Text)

class VectorDBSnapshot(Base):
    __tablename__ = 'vector_db_snapshots'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    total_vectors: Mapped[int | None] = mapped_column(BigInteger, default=0)
    storage_mb: Mapped[float | None] = mapped_column('storage_used_mb', Float, default=0)
    index_count: Mapped[int | None] = mapped_column(Integer, default=0)
    shard_count: Mapped[int | None] = mapped_column(Integer, default=1)
    avg_search_latency_ms: Mapped[float | None] = mapped_column('avg_retrieve_ms', Float, default=0)
    p95_search_latency_ms: Mapped[float | None] = mapped_column('p95_retrieve_ms', Float, default=0)
    search_success_rate: Mapped[float | None] = mapped_column('success_rate', Float, default=1)
    recall_rate: Mapped[float | None] = mapped_column(Float, default=1)
    health_score: Mapped[float | None] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column('recorded_at', DateTime, default=utcnow)


class UserPaperNote(Base):
    __tablename__ = 'user_paper_notes'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id'), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[list | dict] = mapped_column(JSON)
    selected_text: Mapped[str] = mapped_column(Text)
    note_content: Mapped[str | None] = mapped_column(Text)
    highlight_color: Mapped[str] = mapped_column(String(20), default='#FFEB3B')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ExplorationTask(Base):
    """用户点击推荐后的探索记录"""
    __tablename__ = 'exploration_tasks'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey('knowledge_domains.id'), index=True)
    concept: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(20), default='relation')  # relation / llm
    status: Mapped[str] = mapped_column(String(20), default='clicked')  # clicked / paper_uploaded / completed
    paper_id: Mapped[int | None] = mapped_column(ForeignKey('papers.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SubjectHierarchy(Base):
    """学科层级关系表 - 由LLM分析生成"""
    __tablename__ = 'subject_hierarchy'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey('papers.id'), index=True)
    subject_label: Mapped[str] = mapped_column(String(200), index=True)
    primary_domain: Mapped[str] = mapped_column(String(200), index=True)
    secondary_domain: Mapped[str | None] = mapped_column(String(200), index=True)
    tertiary_domain: Mapped[str | None] = mapped_column(String(200), index=True)
    domain_path: Mapped[str] = mapped_column(String(500))
    is_core: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
