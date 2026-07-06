from contextlib import asynccontextmanager
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.mysql import AsyncSessionLocal, create_all_tables
from app.models import ModelConfig, TaskSchedulerConfig, User
from app.utils.json_utils import dumps
settings = get_settings()
logger = logging.getLogger(__name__)

async def seed_initial_data() -> None:
    async with AsyncSessionLocal() as db:
        admin = (await db.execute(select(User).where(User.username == settings.demo_admin_username))).scalar_one_or_none()
        if not admin:
            db.add(User(username=settings.demo_admin_username, password_hash=hash_password(settings.demo_admin_password), name='系统管理员', role='admin', status='active', quota_json=dumps({'single_file_max_mb': settings.default_single_file_max_mb, 'total_papers': settings.default_total_papers, 'daily_qa_calls': settings.default_daily_qa_calls, 'concurrent_tasks': settings.default_concurrent_tasks, 'vector_storage_mb': 10240, 'alert_threshold': 0.8})))
        exists = (await db.execute(select(ModelConfig))).first()
        if not exists:
            db.add_all([
                ModelConfig(model_type='parse', model_name='GROBID+PyMuPDF+pdfplumber', version='0.8.0/1.25/0.11', api_endpoint=settings.grobid_base_url, config_json=dumps({'engine_chain':['GROBID','PyMuPDF','pdfplumber']}), is_active=True),
                ModelConfig(model_type='vector', model_name=settings.bge_embedding_model, version='BGE', api_endpoint='local://sentence-transformers', config_json=dumps({'dim': settings.milvus_vector_dim, 'normalize': True}), is_active=True),
                ModelConfig(model_type='reranker', model_name=settings.bge_reranker_model, version='BGE', api_endpoint='local://sentence-transformers', config_json=dumps({'top_n': settings.rerank_top_n}), is_active=True),
            ])
        if not (await db.execute(select(TaskSchedulerConfig))).first():
            db.add(TaskSchedulerConfig(max_concurrent_tasks=4, per_user_concurrent=2, timeout_seconds=300))
        await db.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.rag_service import warmup_rag_models

    await create_all_tables()
    await seed_initial_data()
    asyncio.create_task(asyncio.to_thread(warmup_rag_models))
    yield

app = FastAPI(title=settings.app_name, version='1.0.0-doc-strict', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

@app.exception_handler(Exception)
async def handle_exception(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={'detail': str(exc), 'path': request.url.path})

@app.get('/health')
async def root_health():
    return {'status':'ok', 'app': settings.app_name, 'env': settings.app_env}

app.include_router(api_router, prefix=settings.api_v1_prefix)
