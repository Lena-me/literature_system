from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from sqlalchemy import or_, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user, get_current_user_brief
from app.db.mysql import AsyncSessionLocal, get_db
from app.db.redis import redis_client
from app.integrations.object_storage.minio_storage import MinioStorage
from app.models import Category, ContentItem, FiguresTable, Paper, ParseTask, User
from app.schemas import CategoryIn, ChunkUploadCompleteIn, ChunkUploadInitIn, PaperOut, PaperUpdateIn
from app.services.audit_service import audit_action
from app.services.parse_status_events import TERMINAL_PARSE_STATUSES, channel_for_user, publish_parse_status
from app.services.quota_service import QuotaService
from app.utils.json_utils import dumps, loads
from app.utils.mineru_text import unwrap_mineru_json_text
from app.workers.celery_app import celery_app

settings = get_settings()
router = APIRouter(prefix='/papers', tags=['文献管理'])

_FIGURE_IMAGE_LINE_RE = re.compile(r'^!\[[^\]]*\]\(([^)]+)\)\s*$')
_DEFAULT_FIGURE_CAPTION = 'Figure extracted by MinerU'


def _build_figure_content_from_db(content: str, figure: FiguresTable) -> str:
    """用 figures_tables.image_path（MinIO URL）组装可渲染的图片 Markdown。"""
    image_url = (figure.image_path or '').strip()
    if not image_url:
        return content

    caption_lines: list[str] = []
    has_image_line = False
    for line in (content or '').split('\n'):
        stripped = line.strip()
        if not stripped:
            continue
        if _FIGURE_IMAGE_LINE_RE.match(stripped):
            has_image_line = True
            continue
        caption_lines.append(stripped)

    caption = '\n'.join(caption_lines).strip()
    if not caption:
        db_caption = (figure.caption or '').strip()
        if db_caption and db_caption != _DEFAULT_FIGURE_CAPTION:
            caption = db_caption
    elif not has_image_line and len(caption_lines) == 1:
        caption = caption_lines[0]

    if caption:
        return f'![]({image_url})\n{caption}'
    return f'![]({image_url})'


async def _create_paper_from_bytes(db: AsyncSession, user: User, filename: str, data: bytes) -> Paper:
    if not filename or not filename.lower().endswith('.pdf'):
        raise HTTPException(400, '仅支持 PDF 文件')

    user_id = user.id
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return await _create_paper_from_bytes_once(db, user_id, filename, data)
        except OperationalError as exc:
            await db.rollback()
            err_no = getattr(getattr(exc, 'orig', None), 'args', [None])[0]
            if err_no != 1213 and '1213' not in str(exc):
                raise
            last_error = exc
            if attempt >= 2:
                raise HTTPException(503, '上传繁忙，请稍后重试') from exc
            await asyncio.sleep(0.08 * (attempt + 1))

    if last_error:
        raise last_error
    raise HTTPException(500, '上传失败')


async def _create_paper_from_bytes_once(db: AsyncSession, user_id: int, filename: str, data: bytes) -> Paper:
    await QuotaService().check_upload(db, user_id, len(data))

    object_key = f'{user_id}/{uuid4().hex}.pdf'
    MinioStorage().put_pdf(object_key, data)

    paper = Paper(
        user_id=user_id,
        original_filename=filename,
        file_size=len(data),
        file_path=f'minio://paper-pdf/{object_key}',
        object_key=object_key,
        parse_status='queued',
    )
    db.add(paper)
    await db.flush()

    task = ParseTask(
        paper_id=paper.id,
        user_id=user_id,
        task_type='document_parse',
        status='queued',
        priority=5,
    )
    db.add(task)
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(paper_upload_count=User.paper_upload_count + 1)
    )

    await audit_action(
        db,
        user_id=user_id,
        module='papers',
        operation_type='upload',
        content={
            'paper_id': paper.id,
            'filename': paper.original_filename,
            'file_size': paper.file_size,
        },
    )
    await db.commit()
    await db.refresh(paper)

    celery_app.send_task(
        'app.workers.tasks.process_paper_pipeline',
        args=[paper.id],
        queue='paper_tasks',
    )
    await asyncio.to_thread(
        publish_parse_status,
        user_id,
        paper.id,
        'queued',
        title=paper.title or paper.original_filename,
    )
    return paper


@router.post('/upload', response_model=PaperOut)
async def upload_paper(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await file.read()
    return await _create_paper_from_bytes(db, user, file.filename or 'paper.pdf', data)


@router.post('/batch-upload', response_model=list[PaperOut])
async def batch_upload_papers(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if len(files) < 2 or len(files) > 10:
        raise HTTPException(400, '批量上传支持 2-10 篇 PDF')

    created: list[Paper] = []
    for f in files:
        created.append(await _create_paper_from_bytes(db, user, f.filename or 'paper.pdf', await f.read()))
    return created


@router.post('/upload/init')
async def init_chunk_upload(
    data: ChunkUploadInitIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not data.filename.lower().endswith('.pdf'):
        raise HTTPException(400, '仅支持 PDF 文件')

    await QuotaService().check_upload(db, user.id, data.total_size)

    upload_id = uuid4().hex
    meta = data.model_dump() | {'user_id': user.id, 'received': []}
    await redis_client.set(f'upload:{upload_id}', dumps(meta), ex=24 * 3600)
    Path(settings.upload_tmp_dir, str(user.id), upload_id).mkdir(parents=True, exist_ok=True)
    return {'upload_id': upload_id, 'message': '分片上传会话已创建'}


@router.put('/upload/chunk')
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    raw = await redis_client.get(f'upload:{upload_id}')
    if not raw:
        raise HTTPException(404, '上传会话不存在或已过期')

    meta = loads(raw, {})
    if int(meta.get('user_id')) != user.id:
        raise HTTPException(403, '无权访问该上传会话')

    total_chunks = int(meta.get('total_chunks', 0))
    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(400, '分片序号非法')

    base = Path(settings.upload_tmp_dir, str(user.id), upload_id)
    base.mkdir(parents=True, exist_ok=True)
    target = base / f'{chunk_index:08d}.part'

    with target.open('wb') as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)

    received = set(meta.get('received') or [])
    received.add(chunk_index)
    meta['received'] = sorted(received)
    await redis_client.set(f'upload:{upload_id}', dumps(meta), ex=24 * 3600)
    return {
        'upload_id': upload_id,
        'chunk_index': chunk_index,
        'received': len(received),
        'total_chunks': total_chunks,
    }


@router.get('/upload/{upload_id}/status')
async def chunk_upload_status(upload_id: str, user: User = Depends(get_current_user)):
    raw = await redis_client.get(f'upload:{upload_id}')
    if not raw:
        raise HTTPException(404, '上传会话不存在或已过期')

    meta = loads(raw, {})
    if int(meta.get('user_id')) != user.id:
        raise HTTPException(403, '无权访问该上传会话')

    return {
        'upload_id': upload_id,
        'filename': meta.get('filename'),
        'received': meta.get('received', []),
        'total_chunks': meta.get('total_chunks'),
    }


@router.post('/upload/complete', response_model=PaperOut)
async def complete_chunk_upload(
    data: ChunkUploadCompleteIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw = await redis_client.get(f'upload:{data.upload_id}')
    if not raw:
        raise HTTPException(404, '上传会话不存在或已过期')

    meta = loads(raw, {})
    if int(meta.get('user_id')) != user.id:
        raise HTTPException(403, '无权访问该上传会话')

    total_chunks = int(meta.get('total_chunks'))
    received = set(meta.get('received') or [])
    missing = [i for i in range(total_chunks) if i not in received]
    if missing:
        raise HTTPException(400, f'仍缺少分片：{missing[:20]}')

    base = Path(settings.upload_tmp_dir, str(user.id), data.upload_id)
    assembled = base / 'assembled.pdf'
    with assembled.open('wb') as out:
        for i in range(total_chunks):
            part = base / f'{i:08d}.part'
            with part.open('rb') as inp:
                shutil.copyfileobj(inp, out)

    pdf_bytes = assembled.read_bytes()
    paper = await _create_paper_from_bytes(db, user, meta.get('filename') or 'paper.pdf', pdf_bytes)
    await redis_client.delete(f'upload:{data.upload_id}')
    shutil.rmtree(base, ignore_errors=True)
    return paper


@router.get('', response_model=list[PaperOut])
async def list_papers(
    keyword: str | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Paper).where(Paper.user_id == user.id, Paper.is_deleted == False)

    if keyword:
        like = f'%{keyword}%'
        stmt = stmt.where(
            or_(Paper.title.like(like), Paper.original_filename.like(like), Paper.journal_conf.like(like))
        )
    if status:
        stmt = stmt.where(Paper.parse_status == status)

    result = await db.execute(stmt.order_by(Paper.upload_time.desc()).offset(skip).limit(limit))
    return result.scalars().all()


@router.get('/parse-events')
async def parse_events_stream(
    user: User = Depends(get_current_user_brief),
):
    """SSE：后端推送文献解析状态（Redis Pub/Sub）。"""
    async with AsyncSessionLocal() as db:
        pending_rows = (
            await db.execute(
                select(Paper.id, Paper.parse_status, Paper.title, Paper.original_filename).where(
                    Paper.user_id == user.id,
                    Paper.is_deleted == False,
                    Paper.parse_status.notin_(list(TERMINAL_PARSE_STATUSES)),
                )
            )
        ).all()
    initial_events = [
        {
            'type': 'parse_status',
            'paper_id': row.id,
            'parse_status': row.parse_status,
            'title': row.title or row.original_filename,
        }
        for row in pending_rows
    ]

    async def gen():
        channel = channel_for_user(user.id)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel)
        try:
            yield f"data: {json.dumps({'type': 'connected'}, ensure_ascii=False)}\n\n"
            for evt in initial_events:
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=25.0)
                if message is None:
                    yield ': keepalive\n\n'
                    continue
                if message.get('type') != 'message':
                    continue
                data = message.get('data')
                if data:
                    yield f'data: {data}\n\n'
        except asyncio.CancelledError:
            return
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(
        gen(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache, no-transform',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@router.get('/parse-status')
async def parse_status(
    ids: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """轻量轮询：仅返回指定文献的 parse_status（避免反复拉全量列表）。"""
    paper_ids: list[int] = []
    for part in (ids or '').split(','):
        part = part.strip()
        if part.isdigit():
            paper_ids.append(int(part))
    if not paper_ids:
        return []
    if len(paper_ids) > 100:
        raise HTTPException(status_code=400, detail='一次最多查询 100 篇文献状态')

    rows = (
        await db.execute(
            select(Paper.id, Paper.parse_status, Paper.title, Paper.original_filename).where(
                Paper.user_id == user.id,
                Paper.is_deleted == False,
                Paper.id.in_(paper_ids),
            )
        )
    ).all()
    return [
        {
            'id': row.id,
            'parse_status': row.parse_status,
            'title': row.title or row.original_filename,
        }
        for row in rows
    ]


@router.get('/categories')
async def list_categories(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        await db.execute(
            select(Category).where(Category.user_id == user.id).order_by(Category.created_at.desc())
        )
    ).scalars().all()
    return [{'id': x.id, 'name': x.name, 'parent_id': x.parent_id, 'created_at': x.created_at} for x in rows]


@router.post('/categories')
async def create_category(data: CategoryIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    category = Category(user_id=user.id, name=data.name, parent_id=data.parent_id)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return {'id': category.id, 'name': category.name, 'parent_id': category.parent_id}


@router.put('/categories/{category_id}')
async def update_category(
    category_id: int,
    data: CategoryIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    category = await db.get(Category, category_id)
    if not category or category.user_id != user.id:
        raise HTTPException(status_code=404, detail='分类不存在')
    category.name = data.name
    if data.parent_id is not None:
        category.parent_id = data.parent_id
    await db.commit()
    await db.refresh(category)
    return {'id': category.id, 'name': category.name, 'parent_id': category.parent_id}


@router.delete('/categories/{category_id}')
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    category = await db.get(Category, category_id)
    if not category or category.user_id != user.id:
        raise HTTPException(status_code=404, detail='分类不存在')
    await db.delete(category)
    await db.commit()
    return {'ok': True}


@router.get('/{paper_id}', response_model=PaperOut)
async def get_paper(paper_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    paper = await db.get(Paper, paper_id)
    if not paper or paper.user_id != user.id or paper.is_deleted:
        raise HTTPException(404, '文献不存在')
    return paper


@router.put('/{paper_id}', response_model=PaperOut)
async def update_paper(
    paper_id: int,
    data: PaperUpdateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    paper = await db.get(Paper, paper_id)
    if not paper or paper.user_id != user.id:
        raise HTTPException(404, '文献不存在')

    for field, value in data.model_dump(exclude_unset=True).items():
        if field in {'authors', 'keywords', 'subject_labels'} and value is not None:
            value = dumps(value)
        setattr(paper, field, value)

    await db.commit()
    await db.refresh(paper)
    return paper


@router.delete('/{paper_id}')
async def delete_paper(paper_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    paper = await db.get(Paper, paper_id)
    if not paper or paper.user_id != user.id:
        raise HTTPException(404, '文献不存在')

    paper.is_deleted = True
    paper.parse_status = 'deleted'
    await audit_action(
        db,
        user_id=user.id,
        module='papers',
        operation_type='delete',
        content={
            'paper_id': paper.id,
            'filename': paper.original_filename,
        },
        risk=1,
    )
    await db.commit()
    return {'message': '已删除'}


@router.get('/{paper_id}/content')
async def paper_content(
    paper_id: int,
    include_all: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    paper = await db.get(Paper, paper_id)
    if not paper or paper.user_id != user.id or paper.is_deleted:
        raise HTTPException(404, '文献不存在')

    rows = (
        await db.execute(
            select(ContentItem).where(ContentItem.paper_id == paper_id).order_by(ContentItem.order_index.asc())
        )
    ).scalars().all()
    figure_rows = (
        await db.execute(
            select(FiguresTable)
            .where(FiguresTable.paper_id == paper_id, FiguresTable.type == 'figure')
            .order_by(FiguresTable.order_index.asc())
        )
    ).scalars().all()
    figure_idx = 0
    result = []
    for r in rows:
        content = r.content or ''
        item_type = r.item_type
        if item_type == 'figure' and figure_idx < len(figure_rows):
            figure = figure_rows[figure_idx]
            figure_idx += 1
            if figure.image_path:
                content = _build_figure_content_from_db(content, figure)
        content = unwrap_mineru_json_text(content)
        result.append(
            {
                'id': r.id,
                'type': item_type,
                'item_type': item_type,
                'level': r.level,
                'content': content,
                'bbox': r.bbox,
                'page_number': r.page_number,
                'order_index': r.order_index,
            }
        )

    if not include_all:
        from app.utils.content_filter import filter_content_items_for_display

        paper_title = paper.title or paper.original_filename
        result = filter_content_items_for_display(result, paper_title=paper_title)

    return result


@router.post('/{paper_id}/reparse')
async def reparse_paper(paper_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    paper = await db.get(Paper, paper_id)
    if not paper or paper.user_id != user.id or paper.is_deleted:
        raise HTTPException(404, '文献不存在')

    await QuotaService().check_upload(db, user.id, paper.file_size)
    paper.parse_status = 'queued'
    task = ParseTask(paper_id=paper.id, user_id=user.id, task_type='document_parse', status='queued')
    db.add(task)
    await db.flush()
    await audit_action(
        db,
        user_id=user.id,
        module='papers',
        operation_type='reparse',
        content={
            'paper_id': paper.id,
            'filename': paper.original_filename,
            'task_id': task.id,
        },
    )
    await db.commit()
    await db.refresh(task)

    celery_app.send_task(
        'app.workers.tasks.process_paper_pipeline',
        args=[paper.id],
        queue='paper_tasks',
    )
    await asyncio.to_thread(
        publish_parse_status,
        user.id,
        paper.id,
        'queued',
        title=paper.title or paper.original_filename,
    )
    return {'message': '已重新加入解析队列', 'task_id': task.id}


@router.get('/{paper_id}/file')
async def paper_file(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    paper = await db.get(Paper, paper_id)

    if not paper:
        raise HTTPException(404, f'文献不存在：paper_id={paper_id}')

    if paper.user_id != user.id:
        raise HTTPException(
            403,
            f'无权访问该文献：paper_id={paper_id}, paper_user_id={paper.user_id}, current_user_id={user.id}',
        )

    if paper.is_deleted:
        raise HTTPException(404, f'文献已删除：paper_id={paper_id}')

    if not paper.object_key:
        raise HTTPException(404, f'该文献没有 PDF object_key：paper_id={paper_id}')

    try:
        data = MinioStorage().get_pdf(paper.object_key)
    except S3Error as exc:
        raise HTTPException(
            404,
            f'PDF 源文件不存在或无法从 MinIO 读取：object_key={paper.object_key}, error={exc.code}',
        ) from exc
    except Exception as exc:
        raise HTTPException(
            500,
            f'PDF 文件读取失败：object_key={paper.object_key}, error={type(exc).__name__}: {str(exc)[:200]}',
        ) from exc

    filename = quote(paper.original_filename or 'paper.pdf')
    return Response(
        content=data,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f"inline; filename*=UTF-8''{filename}",
            'Content-Length': str(len(data)),
            'Cache-Control': 'no-store',
        },
    )


@router.get('/{paper_id}/file-url')
async def paper_file_url(paper_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    paper = await db.get(Paper, paper_id)
    if not paper or paper.user_id != user.id or paper.is_deleted:
        raise HTTPException(404, '文献不存在')
    return {'url': MinioStorage().presigned_pdf_url(paper.object_key)}
