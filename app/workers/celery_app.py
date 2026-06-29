from celery import Celery
from app.core.config import get_settings
settings = get_settings()
celery_app = Celery('paper_knowledge_workers', broker=settings.celery_broker_url, backend=settings.celery_result_backend, include=['app.workers.tasks'])
celery_app.conf.task_routes = {'app.workers.tasks.*': {'queue': 'paper_tasks'}}
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.task_track_started = True
