from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import User
from app.schemas import CompareIn
from app.services.generation_service import GenerationService
from app.utils.json_utils import loads
router = APIRouter(prefix='/comparisons', tags=['多文献对比'])

@router.post('')
async def compare(data: CompareIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await GenerationService().compare_papers(db, user.id, data.paper_ids, data.dimensions, data.name)
    return {'id': obj.id, 'name': obj.name, 'paper_ids': loads(obj.paper_ids), 'result': loads(obj.result_json), 'created_at': obj.created_at}
