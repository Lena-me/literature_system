from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import LearningRecord, Paper, QAMessage, QASession, Report, User
from app.schemas import LearningRecordIn
from app.utils.json_utils import dumps, loads
router = APIRouter(prefix='/learning-records', tags=['学习档案'])

@router.post('')
async def create_record(data: LearningRecordIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = LearningRecord(user_id=user.id, paper_id=data.paper_id, event_type=data.event_type, event_data=dumps(data.event_data or {}))
    db.add(obj); await db.commit(); await db.refresh(obj)
    return {'id': obj.id}

def _generate_upload_heatmap_data(db_result: list[tuple]) -> dict:
    upload_counts: dict[str, int] = {}
    for row in db_result:
        dt, count = row
        if isinstance(dt, datetime):
            dt = dt.date()
        date_str = dt.strftime('%Y-%m-%d')
        upload_counts[date_str] = int(count)

    today = date.today()
    months = []
    for i in range(11, -1, -1):
        month_start = (today - timedelta(days=i * 30)).replace(day=1)
        months.append(month_start.strftime('%Y-%m'))

    month_data: dict[str, list[int]] = {}
    for month_str in months:
        year, month = map(int, month_str.split('-'))
        days_in_month = (datetime(year, month + 1, 1) - timedelta(days=1)).day if month < 12 else 31
        month_data[month_str] = [0] * days_in_month
        for day in range(1, days_in_month + 1):
            date_str = f'{year:04d}-{month:02d}-{day:02d}'
            if date_str in upload_counts:
                month_data[month_str][day - 1] = upload_counts[date_str]

    return {
        'months': months,
        'data': month_data,
        'max_value': max(upload_counts.values(), default=1),
    }

@router.get('/overview')
async def overview(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    paper_count = (await db.execute(select(func.count()).select_from(Paper).where(Paper.user_id == user.id, Paper.is_deleted == False))).scalar_one()
    report_count = (await db.execute(select(func.count()).select_from(Report).where(Report.user_id == user.id))).scalar_one()
    qa_count = (await db.execute(select(func.count()).select_from(QAMessage).join(QASession, QAMessage.session_id == QASession.id).where(QASession.user_id == user.id, QAMessage.role == 'user'))).scalar_one()
    records = (await db.execute(select(LearningRecord).where(LearningRecord.user_id == user.id).order_by(LearningRecord.created_at.desc()).limit(50))).scalars().all()
    papers = (await db.execute(select(Paper).where(Paper.user_id == user.id, Paper.is_deleted == False).order_by(Paper.upload_time.desc()).limit(200))).scalars().all()
    keyword_cloud: dict[str, int] = {}
    for paper in papers:
        for raw in [paper.keywords, paper.subject_labels]:
            value = loads(raw, []) if isinstance(raw, str) else (raw or [])
            if isinstance(value, str):
                value = [x.strip() for x in value.replace('，', ',').split(',') if x.strip()]
            if isinstance(value, list):
                for item in value[:10]:
                    name = str(item).strip()
                    if name:
                        keyword_cloud[name] = keyword_cloud.get(name, 0) + 1
    if not keyword_cloud:
        keyword_cloud = {'RAG': 8, 'Agent': 6, '文献解析': 7, '知识图谱': 5, '实验复现': 4}

    today = date.today()
    one_year_ago = today - timedelta(days=365)
    upload_stats = (await db.execute(
        select(func.date(Paper.upload_time), func.count())
        .where(Paper.user_id == user.id, Paper.is_deleted == False, Paper.upload_time >= one_year_ago)
        .group_by(func.date(Paper.upload_time))
    )).all()
    heatmap_data = _generate_upload_heatmap_data(upload_stats)

    record_items = [{'id': r.id, 'paper_id': r.paper_id, 'event_type': r.event_type, 'event_data': loads(r.event_data,{}), 'created_at': r.created_at} for r in records]
    return {
        'paper_count': paper_count,
        'report_count': report_count,
        'qa_count': qa_count,
        'records': record_items,
        'recent_records': record_items,
        'keyword_cloud': keyword_cloud,
        'upload_heatmap': heatmap_data,
    }
