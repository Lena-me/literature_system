import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Docker Compose 通过 env_file 注入环境变量，以此区分 env 文件
_env_file = '.env.docker' if os.getenv('APP_ENV') == 'docker' else '.env'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file,
        env_file_encoding='utf-8',
        extra='ignore',
    )

    app_name: str = '科研文献智能解析与知识服务系统后端'
    app_env: str = 'development'
    api_v1_prefix: str = '/api/v1'
    secret_key: str = Field(default='replace-me')
    access_token_expire_minutes: int = 1440
    cors_origins: str = 'http://localhost:5173,http://127.0.0.1:5173'

    # MySQL
    mysql_dsn: str

    # Web 请求连接池：小连接池，避免 NullPool 导致每个请求都重新建连。
    mysql_pool_pre_ping: bool = True
    mysql_pool_size: int = 5
    mysql_max_overflow: int = 10
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
    hf_cache_dir: str = './runtime/hf_cache'
    bge_embedding_model: str = 'BAAI/bge-large-zh-v1.5'
    bge_reranker_model: str = 'BAAI/bge-reranker-large'
    embedding_device: str = 'cpu'
    reranker_device: str = 'cpu'
    chunk_size: int = 900
    chunk_overlap: int = 120
    top_k: int = 8
    rerank_top_n: int = 5

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

    # LLM
    llm_base_url: str
    llm_api_key: str = 'sk-24745623d5bb4b21bd9d85374627bbe6'
    llm_model: str = 'deepseek-v4-pro'
    llm_temperature: float = 0.2
    llm_max_tokens: int = 2048

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