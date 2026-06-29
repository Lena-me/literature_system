from fastapi import APIRouter, Depends
from app.core.dependencies import get_current_user
from app.models import User
from app.schemas import UserOut
router = APIRouter(prefix='/users', tags=['用户'])

@router.get('/me', response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
