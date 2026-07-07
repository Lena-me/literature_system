from functools import lru_cache
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_env_file():
    env = os.getenv('APP_ENV', 'development')
    if env == 'local':
        return '.env.local'
    elif env == 'docker':
        return '.env.docker'
    elif env == 'gpu':
        return '.env.gpu'
    else:
        return '.env'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding='utf-8',
        extra='ignore',
    )

    app_name: str = '睿识'
    app_env: str = 'development'
    api_v1_prefix: str = '/api/v1'
    secret_key: str = Field(default='replace-me')
    # 模型 config_json 中 api_key 的 AES 加密主密钥；未设置时回退 secret_key
    model_config_secret_key: str = ''
    access_token_expire_minutes: int = 1440
    cors_origins: str = 'http://localhost:5173,http://127.0.0.1:5173'

    # MySQL
    mysql_dsn: str

    # Web 请求连接池：小连接池，避免 NullPool 导致每个请求都重新建连。
    mysql_pool_pre_ping: bool = True
    mysql_pool_size: int = 10
    mysql_max_overflow: int = 15
    mysql_pool_recycle_seconds: int = 1800
    mysql_pool_timeout_seconds: int = 30
    mysql_connect_timeout_seconds: int = 10
    mysql_connect_retries: int = 3

    # Redis / Celery
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str

    # MinIO
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket_papers: str
    minio_bucket_exports: str
    minio_secure: bool = False

    # Milvus
    milvus_host: str = '127.0.0.1'
    milvus_port: int = 19530
    milvus_collection: str = 'paper_chunks'
    milvus_vector_dim: int = 1024
    milvus_index_type: str = 'HNSW'
    milvus_metric_type: str = 'COSINE'

    # 解析 / 向量化 / RAG
    grobid_base_url: str = 'http://127.0.0.1:8070'

    # Document Parser
    document_parser: str = 'hybrid'  # grobid / mineru / hybrid
    mineru_command: str = 'mineru'
    mineru_backend: str = 'pipeline'
    mineru_method: str = 'auto'
    mineru_language: str | None = 'ch'
    mineru_api_url: str | None = None
    mineru_output_dir: str = './runtime/mineru_outputs'
    mineru_timeout_seconds: int = 900
    mineru_keep_output: bool = True
    mineru_fallback_to_grobid: bool = True

    # 公式 OCR（RapidLaTeXOCR）
    formula_ocr_enabled: bool = True

    hf_endpoint: str = 'https://hf-mirror.com'
    hf_cache_dir: str = './runtime/hf_cache'
    bge_embedding_model: str = 'BAAI/bge-large-zh-v1.5'
    bge_reranker_model: str = 'BAAI/bge-reranker-large'
    embedding_device: str = 'cpu'
    reranker_device: str = 'cpu'
    chunk_size: int = 900
    chunk_overlap: int = 120
    top_k: int = 8
    rerank_top_n: int = 5
    rag_search_multiplier: int = 3
    rag_rerank_pool_max: int = 12
    rag_enable_reranker: bool = True
    rag_fast_multi_paper: bool = False
    rag_chunk_context_max_chars: int = 900
    rag_rerank_text_max_chars: int = 384

    # 验证码、账号锁定、资源配额、分片上传
    verification_code_ttl_seconds: int = 300
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    default_single_file_max_mb: int = 200
    default_total_papers: int = 1000
    default_daily_qa_calls: int = 200
    default_concurrent_tasks: int = 5
    upload_tmp_dir: str = './runtime/uploads'

    # Milvus 备份恢复
    milvus_backup_dir: str = './runtime/milvus_backups'
    milvus_backup_command: str | None = None
    milvus_restore_command: str | None = None

    # LLM（连接参数仅在管理后台 model_configs 中配置）
    enable_llm_extract: bool = False
    # QA Agent（LangGraph）
    qa_use_langgraph: bool = True
    qa_history_limit: int = 20
    qa_use_llm_rewrite: bool = False
    qa_use_llm_intent: bool = False
    qa_tool_fallback_rag: bool = True

    # Neo4j
    neo4j_uri: str = 'bolt://127.0.0.1:7687'
    neo4j_user: str = 'neo4j'
    neo4j_password: str = 'neo4j'
    neo4j_max_connection_pool_size: int = 10
    neo4j_connection_acquisition_timeout: int = 30

    # Demo
    demo_admin_username: str = 'admin'
    demo_admin_password: str = 'admin123456'

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(',') if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
