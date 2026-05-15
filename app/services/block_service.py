from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, status

from ..models.blocked_worker import BlockedWorker
from ..models.user import User

class BlockService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def block_worker(self, employer_id: int, worker_id: int):
        """Block a worker from applying to an employer's jobs."""
        if employer_id == worker_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot block yourself.",
            )

        # Check if the relationship already exists
        query = select(BlockedWorker).where(
            BlockedWorker.employer_id == employer_id,
            BlockedWorker.worker_id == worker_id
        )
        result = await self.db.execute(query)
        if result.scalars().first():
            return

        block = BlockedWorker(employer_id=employer_id, worker_id=worker_id)
        self.db.add(block)
        await self.db.commit()

    async def unblock_worker(self, employer_id: int, worker_id: int):
        """Unblock a worker."""
        query = select(BlockedWorker).where(
            BlockedWorker.employer_id == employer_id,
            BlockedWorker.worker_id == worker_id
        )
        result = await self.db.execute(query)
        block = result.scalars().first()

        if block:
            await self.db.delete(block)
            await self.db.commit()

    async def is_worker_blocked(self, employer_id: int, worker_id: int) -> bool:
        """Check if a worker is blocked by an employer."""
        query = select(BlockedWorker).where(
            BlockedWorker.employer_id == employer_id,
            BlockedWorker.worker_id == worker_id
        )
        result = await self.db.execute(query)
        return result.scalars().first() is not None
