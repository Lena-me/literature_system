from enum import StrEnum

class UserRole(StrEnum):
    RESEARCHER = "researcher"
    ADMIN = "admin"

class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"

class ParseStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    EXTRACTING = "extracting"
    VECTORIZING = "vectorizing"
    INDEX_READY = "index_ready"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskType(StrEnum):
    DOCUMENT_PARSE = "document_parse"
    INFO_EXTRACTION = "info_extraction"
    VECTORIZATION = "vectorization"
    REPORT_GENERATION = "report_generation"
    GRAPH_GENERATION = "graph_generation"
    REPRO_GUIDE = "repro_guide"

class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ModelType(StrEnum):
    PARSE = "parse"
    VECTOR = "vector"
    RERANKER = "reranker"
    LLM = "llm"

class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
