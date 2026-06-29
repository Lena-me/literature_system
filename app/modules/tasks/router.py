from __future__ import annotations
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import require_admin
from app.core.security import decode_access_token
from app.db.mysql import AsyncSessionLocal, get_db
from app.models import ParseTask, TaskSchedulerConfig, User
from app.schemas import SchedulerConfigIn, TaskBatchRetryIn, TaskPriorityIn
from app.utils.json_utils import dumps, loads
from app.workers.celery_app import celery_app
router = APIRouter(prefix='/tasks', tags=['解析任务管理'])

@router.get('')
async def list_tasks(status: str | None = None, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    stmt = select(ParseTask)
    if status: stmt = stmt.where(ParseTask.status == status)
    rows = (await db.execute(stmt.order_by(ParseTask.priority.asc(), ParseTask.created_at.desc()).limit(300))).scalars().all()
    return [{'id': x.id, 'paper_id': x.paper_id, 'user_id': x.user_id, 'task_type': x.task_type, 'status': x.status, 'priority': x.priority, 'queue_position': x.queue_position, 'start_time': x.start_time, 'end_time': x.end_time, 'duration_ms': x.duration_ms, 'retry_count': x.retry_count, 'error_log': x.error_log, 'created_at': x.created_at} for x in rows]

@router.post('/{task_id}/cancel')
async def cancel_task(task_id: int, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    task = await db.get(ParseTask, task_id)
    if not task: raise HTTPException(404, '任务不存在')
    if task.status in {'completed','failed','cancelled'}: raise HTTPException(400, '当前状态不允许终止')
    task.status = 'cancelled'; await db.commit(); return {'message':'已终止'}

@router.post('/{task_id}/retry')
async def retry_task(task_id: int, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    task = await db.get(ParseTask, task_id)
    if not task: raise HTTPException(404, '任务不存在')
    if task.status not in {'failed','cancelled'}: raise HTTPException(400, '只有失败或已终止任务可重试')
    task.status = 'queued'; task.error_log = None; task.retry_count += 1; task.queue_position = None
    await db.commit()
    celery_app.send_task(
        'app.workers.tasks.process_paper_pipeline',
        args=[task.paper_id],
        queue='paper_tasks'
    )
    return {'message':'已重新加入队列', 'task_id': task.id}

@router.post('/batch-retry')
async def batch_retry(data: TaskBatchRetryIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    rows = (await db.execute(select(ParseTask).where(ParseTask.id.in_(data.task_ids)))).scalars().all()
    retried = []
    for task in rows:
        if task.status in {'failed','cancelled'}:
            task.status = 'queued'; task.error_log = None; task.retry_count += 1
            celery_app.send_task(
                'app.workers.tasks.process_paper_pipeline',
                args=[task.paper_id],
                queue='paper_tasks'
            )
            retried.append(task.id)
    await db.commit()
    return {'retried_task_ids': retried}

@router.put('/{task_id}/priority')
async def set_priority(task_id: int, data: TaskPriorityIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    task = await db.get(ParseTask, task_id)
    if not task: raise HTTPException(404, '任务不存在')
    task.priority = data.priority
    await db.commit()
    return {'message':'优先级已调整', 'task_id': task.id, 'priority': task.priority}

@router.get('/failure-stats')
async def failure_stats(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    rows = (await db.execute(select(ParseTask.error_log, func.count(ParseTask.id)).where(ParseTask.status == 'failed').group_by(ParseTask.error_log).limit(20))).all()
    total = (await db.execute(select(func.count(ParseTask.id)).where(ParseTask.status == 'failed'))).scalar() or 0
    return {'failed_total': total, 'by_reason': [{'reason': (r[0] or 'unknown')[:200], 'count': r[1]} for r in rows]}


@router.websocket('/{task_id}/ws')
async def task_websocket(task_id: int, websocket: WebSocket):
    token = websocket.query_params.get('token')
    if not token:
        await websocket.close(code=1008)
        return
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get('sub'))
    except Exception:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        last = None
        for _ in range(3600):
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                task = await db.get(ParseTask, task_id)
                if not user or not task or (user.role != 'admin' and task.user_id != user.id):
                    await websocket.send_json({'type': 'error', 'message': '任务不存在或无权访问'})
                    await websocket.close(code=1008)
                    return
                payload = {
                    'type': 'task',
                    'id': task.id,
                    'paper_id': task.paper_id,
                    'status': task.status,
                    'queue_position': task.queue_position,
                    'priority': task.priority,
                    'start_time': task.start_time.isoformat() if task.start_time else None,
                    'end_time': task.end_time.isoformat() if task.end_time else None,
                    'duration_ms': task.duration_ms,
                    'error_log': task.error_log,
                }
                if payload != last:
                    await websocket.send_json(payload)
                    last = payload
                if task.status in {'completed', 'failed', 'cancelled'}:
                    await websocket.send_json({'type': 'done', 'status': task.status})
                    return
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return

@router.get('/{task_id}/events')
async def task_events(task_id: int, admin: User = Depends(require_admin)):
    async def gen():
        last = None
        for _ in range(3600):
            async with AsyncSessionLocal() as db:
                task = await db.get(ParseTask, task_id)
                if not task:
                    yield f"data: {json.dumps({'type':'error','message':'任务不存在'}, ensure_ascii=False)}\n\n"; return
                payload = {'id': task.id, 'status': task.status, 'queue_position': task.queue_position, 'start_time': task.start_time.isoformat() if task.start_time else None, 'end_time': task.end_time.isoformat() if task.end_time else None, 'error_log': task.error_log}
                if payload != last:
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"; last = payload
                if task.status in {'completed','failed','cancelled'}:
                    return
            await asyncio.sleep(1)
    return StreamingResponse(gen(), media_type='text/event-stream')

@router.get('/scheduler-config')
async def get_config(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    obj = (await db.execute(select(TaskSchedulerConfig).order_by(TaskSchedulerConfig.id.asc()))).scalar_one_or_none()
    return {'max_concurrent_tasks': obj.max_concurrent_tasks, 'per_user_concurrent': obj.per_user_concurrent, 'timeout_seconds': obj.timeout_seconds, 'alert_rules': loads(obj.alert_rules,{}), 'backup_engine_config': loads(obj.backup_engine_config,{})} if obj else {}

@router.put('/scheduler-config')
async def set_config(data: SchedulerConfigIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    obj = (await db.execute(select(TaskSchedulerConfig).order_by(TaskSchedulerConfig.id.asc()))).scalar_one_or_none() or TaskSchedulerConfig()
    obj.max_concurrent_tasks=data.max_concurrent_tasks; obj.per_user_concurrent=data.per_user_concurrent; obj.timeout_seconds=data.timeout_seconds; obj.alert_rules=dumps(data.alert_rules or {}); obj.backup_engine_config=dumps(data.backup_engine_config or {})
    db.add(obj); await db.commit(); return {'message':'已保存'}
