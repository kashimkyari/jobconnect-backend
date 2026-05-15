from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from ..models.recent_activity import RecentActivity
from ..schemas.recent_activity import RecentActivityCreate

class RecentActivityService:
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def create_activity(self, activity_create: RecentActivityCreate) -> RecentActivity:
        new_activity = RecentActivity(**activity_create.dict())
        self.db_session.add(new_activity)
        await self.db_session.commit()
        await self.db_session.refresh(new_activity)
        return new_activity

    async def get_activities_for_user(
        self, user_id: int, skip: int = 0, limit: int = 10
    ) -> List[RecentActivity]:
        result = await self.db_session.execute(
            select(RecentActivity)
            .where(RecentActivity.user_id == user_id)
            .order_by(RecentActivity.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_all_activities(self, skip: int = 0, limit: int = 10) -> List[RecentActivity]:
        result = await self.db_session.execute(
            select(RecentActivity)
            .order_by(RecentActivity.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()
