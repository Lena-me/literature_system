from __future__ import annotations
import asyncio
import os
import shlex
from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.dependencies import require_admin
from app.db.mysql import get_db
from app.integrations.milvus.client import MilvusChunkStore
from app.models import User, VectorBackup, VectorDBSnapshot, VectorRestoreTask
from app.schemas import VectorRestoreIn
settings = get_settings()
router = APIRouter(prefix='/vector-store', tags=['向量库管理'])

@router.get('/stats')
async def stats(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    stat = MilvusChunkStore().stats()
    snap = VectorDBSnapshot(total_vectors=stat.get('total_vectors', 0), storage_mb=stat.get('storage_mb', 0), index_count=stat.get('index_count', 1), shard_count=stat.get('shard_count', 1), avg_search_latency_ms=stat.get('avg_search_latency_ms', 0), p95_search_latency_ms=stat.get('p95_search_latency_ms', 0), search_success_rate=stat.get('search_success_rate', 1), recall_rate=stat.get('recall_rate', 1), health_score=stat.get('health_score', 100))
    db.add(snap); await db.commit()
    return stat

@router.get('/backups')
async def list_backups(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    rows = (await db.execute(select(VectorBackup).order_by(VectorBackup.created_at.desc()).limit(100))).scalars().all()
    return [{'id': x.id, 'backup_type': x.backup_type, 'backup_time': x.backup_time, 'file_size_mb': x.file_size_mb, 'file_location': x.file_location, 'retention_count': x.retention_count, 'status': x.status} for x in rows]

async def _run_optional_command(command: str | None, env: dict[str, str]) -> tuple[str, str]:
    if not command:
        return 'skipped', '未配置外部 milvus-backup 命令，仅完成 Milvus flush 与备份元数据登记'
    proc = await asyncio.create_subprocess_shell(command, env={**os.environ, **env}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError((err or out).decode('utf-8', 'ignore'))
    return 'executed', (out or b'').decode('utf-8', 'ignore')

@router.post('/backups')
async def create_backup(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    Path(settings.milvus_backup_dir).mkdir(parents=True, exist_ok=True)
    backup_name = f"paper_chunks_{datetime.now(BEIJING_TZ).strftime('%Y%m%d%H%M%S')}"
    location = str(Path(settings.milvus_backup_dir) / backup_name)
    obj = VectorBackup(backup_type='manual', file_location=location, status='in_progress')
    db.add(obj); await db.commit(); await db.refresh(obj)
    try:
        MilvusChunkStore().flush()
        status, output = await _run_optional_command(settings.milvus_backup_command, {'MILVUS_COLLECTION': settings.milvus_collection, 'BACKUP_NAME': backup_name, 'BACKUP_LOCATION': location})
        obj.status = 'completed'
        if Path(location).exists():
            obj.file_size_mb = sum(p.stat().st_size for p in Path(location).rglob('*') if p.is_file()) / 1024 / 1024
        await db.commit()
        return {'id': obj.id, 'status': obj.status, 'file_location': location, 'command_status': status, 'output': output[:1000]}
    except Exception as exc:
        obj.status = 'failed'; await db.commit()
        raise HTTPException(500, f'向量库备份失败：{exc}')

@router.post('/restore')
async def restore_backup(data: VectorRestoreIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    backup = await db.get(VectorBackup, data.backup_id)
    if not backup:
        raise HTTPException(404, '备份记录不存在')
    task = VectorRestoreTask(backup_id=backup.id, restore_progress=0, status='in_progress')
    db.add(task); await db.commit(); await db.refresh(task)
    try:
        status, output = await _run_optional_command(settings.milvus_restore_command, {'BACKUP_ID': str(backup.id), 'BACKUP_LOCATION': backup.file_location, 'MILVUS_COLLECTION': settings.milvus_collection})
        task.restore_progress = 100; task.status = 'completed'; task.finished_at = datetime.now(BEIJING_TZ)
        await db.commit()
        return {'restore_task_id': task.id, 'status': task.status, 'command_status': status, 'output': output[:1000]}
    except Exception as exc:
        task.status = 'failed'; task.error_log = repr(exc); task.finished_at = datetime.now(BEIJING_TZ); await db.commit()
        raise HTTPException(500, f'恢复失败：{exc}')
