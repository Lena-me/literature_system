from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import Report, User
from app.schemas import ReportCreateIn
from app.services.generation_service import GenerationService
from app.utils.json_utils import loads
router = APIRouter(prefix='/reports', tags=['研读报告'])

@router.post('')
async def create_report(data: ReportCreateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        obj = await GenerationService().create_report(db, user.id, data.paper_id, data.modules, data.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user.report_generate_count += 1
    await db.commit()
    return {
        'id': obj.id,
        'paper_id': obj.paper_id,
        'title': obj.title,
        'content': loads(obj.content),
        'created_at': obj.created_at,
    }

@router.get('')
async def list_reports(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(Report).where(Report.user_id == user.id).order_by(Report.created_at.desc()))).scalars().all()
    return [{'id': x.id, 'paper_id': x.paper_id, 'title': x.title, 'content': loads(x.content), 'created_at': x.created_at} for x in rows]

@router.delete('/{report_id}')
async def delete_report(report_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    if not report or report.user_id != user.id:
        raise HTTPException(404, '报告不存在')
    await db.delete(report)
    await db.commit()
    return {'message': 'deleted'}

from fastapi.responses import Response
from io import BytesIO
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

@router.get('/{report_id}/export')
async def export_report(report_id: int, format: str = 'md', db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    if not report or report.user_id != user.id:
        raise HTTPException(404, '报告不存在')
    content = loads(report.content, {})
    markdown = content.get('markdown') or str(content)
    safe_title = (report.title or f'report-{report.id}').replace('/', '_')
    if format == 'docx':
        doc = Document()
        doc.add_heading(report.title, level=1)
        for line in markdown.splitlines():
            if line.startswith('# '): doc.add_heading(line[2:], level=1)
            elif line.startswith('## '): doc.add_heading(line[3:], level=2)
            elif line.strip(): doc.add_paragraph(line)
        bio = BytesIO(); doc.save(bio)
        return Response(bio.getvalue(), media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document', headers={'Content-Disposition': f'attachment; filename="{safe_title}.docx"'})
    if format == 'pdf':
        font_name = 'Helvetica'
        for font_path in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc']:
            try:
                pdfmetrics.registerFont(TTFont('NotoCJK', font_path))
                font_name = 'NotoCJK'
                break
            except Exception:
                pass
        bio = BytesIO(); c = canvas.Canvas(bio, pagesize=A4); width, height = A4
        y = height - 50; c.setFont(font_name, 10)
        for raw in markdown.splitlines():
            text = raw.strip() or ' '
            # 简单中文换行：避免 drawString 超出页面。
            lines = [text[i:i+46] for i in range(0, len(text), 46)] or [' ']
            for line in lines:
                if y < 50: c.showPage(); c.setFont(font_name, 10); y = height - 50
                c.drawString(45, y, line); y -= 16
        c.save()
        return Response(bio.getvalue(), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{safe_title}.pdf"'})
    return Response(markdown.encode('utf-8'), media_type='text/markdown; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{safe_title}.md"'})
