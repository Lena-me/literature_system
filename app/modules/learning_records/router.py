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
    record_items = [{'id': r.id, 'paper_id': r.paper_id, 'event_type': r.event_type, 'event_data': loads(r.event_data,{}), 'created_at': r.created_at} for r in records]
    return {
        'paper_count': paper_count,
        'report_count': report_count,
        'qa_count': qa_count,
        'records': record_items,
        'recent_records': record_items,
        'keyword_cloud': keyword_cloud,
    }
