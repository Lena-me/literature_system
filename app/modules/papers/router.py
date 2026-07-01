from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from minio.error import S3Error
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.db.redis import redis_client
from app.integrations.object_storage.minio_storage import MinioStorage
from app.models import Category, ContentItem, Paper, ParseTask, User
from app.schemas import CategoryIn, ChunkUploadCompleteIn, ChunkUploadInitIn, PaperOut, PaperUpdateIn
from app.services.quota_service import QuotaService
from app.utils.json_utils import dumps, loads
from app.workers.celery_app import celery_app

settings = get_settings()
router = APIRouter(prefix='/papers', tags=['文献管理'])


async def _create_paper_from_bytes(db: AsyncSession, user: User, filename: str, data: bytes) -> Paper:
    if not filename or not filename.lower().endswith('.pdf'):
        raise HTTPException(400, '仅支持 PDF 文件')

    await QuotaService().check_upload(db, user, len(data))

    object_key = f'{user.id}/{uuid4().hex}.pdf'
    MinioStorage().put_pdf(object_key, data)

    paper = Paper(
        user_id=user.id,
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
        user_id=user.id,
        task_type='document_parse',
        status='queued',
        priority=5,
    )
    db.add(task)
    user.paper_upload_count += 1

    await db.commit()
    await db.refresh(paper)

    celery_app.send_task(
        'app.workers.tasks.process_paper_pipeline',
        args=[paper.id],
        queue='paper_tasks',
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

    await QuotaService().check_upload(db, user, data.total_size)

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
    await db.commit()
    return {'message': '已删除'}


@router.get('/{paper_id}/content')
async def paper_content(paper_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    paper = await db.get(Paper, paper_id)
    if not paper or paper.user_id != user.id or paper.is_deleted:
        raise HTTPException(404, '文献不存在')

    rows = (
        await db.execute(
            select(ContentItem).where(ContentItem.paper_id == paper_id).order_by(ContentItem.order_index.asc())
        )
    ).scalars().all()
    return [
        {
            'id': r.id,
            'type': r.item_type,
            'level': r.level,
            'content': r.content,
            'page_number': r.page_number,
            'order_index': r.order_index,
        }
        for r in rows
    ]


@router.post('/{paper_id}/reparse')
async def reparse_paper(paper_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    paper = await db.get(Paper, paper_id)
    if not paper or paper.user_id != user.id or paper.is_deleted:
        raise HTTPException(404, '文献不存在')

    await QuotaService().check_upload(db, user, paper.file_size)
    paper.parse_status = 'queued'
    task = ParseTask(paper_id=paper.id, user_id=user.id, task_type='document_parse', status='queued')
    db.add(task)
    await db.commit()
    await db.refresh(task)

    celery_app.send_task(
        'app.workers.tasks.process_paper_pipeline',
        args=[paper.id],
        queue='paper_tasks',
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
