from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import User
from app.schemas import ReproGuideCreateIn
from app.services.generation_service import GenerationService
from app.utils.json_utils import loads
router = APIRouter(prefix='/experiments', tags=['实验复现建议'])

@router.post('/reproducibility-guides')
async def create_guide(data: ReproGuideCreateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await GenerationService().create_repro_guide(db, user.id, data.paper_id)
    return {'id': obj.id, 'paper_id': obj.paper_id, 'guide_content': loads(obj.guide_content), 'created_at': obj.created_at}
