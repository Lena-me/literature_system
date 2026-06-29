from typing import TypeVar, Generic, Type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.base import Base

T = TypeVar('T', bound=Base)

class Repository(Generic[T]):
    def __init__(self, model: Type[T], db: AsyncSession):
        self.model = model
        self.db = db

    async def get(self, object_id: int) -> T | None:
        return await self.db.get(self.model, object_id)

    async def add(self, obj: T) -> T:
        self.db.add(obj)
        await self.db.flush()
        return obj

    async def list(self, offset: int = 0, limit: int = 20):
        result = await self.db.execute(select(self.model).offset(offset).limit(limit))
        return result.scalars().all()

    async def count(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(self.model))
        return int(result.scalar_one())
