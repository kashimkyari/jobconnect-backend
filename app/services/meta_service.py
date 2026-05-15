from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List

from ..models.user import User
from ..models.worker_profile import UserService

class MetaService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_unique_services(self) -> List[str]:
        result = await self.db.execute(select(UserService.service_name).distinct())
        return [row[0] for row in result.all() if row[0]]

    async def get_unique_categories(self) -> List[str]:
        result = await self.db.execute(select(User.service_category).distinct())
        return [row[0] for row in result.all() if row[0]]

    async def get_common_skills(self) -> List[str]:
        # This is a simplified approach. For a production system, you might want to
        # implement a more sophisticated method to determine "common" skills.
        result = await self.db.execute(
            select(func.jsonb_array_elements_text(User.skills)).distinct().limit(50)
        )
        return [row[0] for row in result.all() if row[0]]

    async def get_distinct_locations(self) -> List[str]:
        result = await self.db.execute(select(User.location).distinct())
        return [row[0] for row in result.all() if row[0]]

    async def get_experience_levels(self) -> List[str]:
        # These values are typically static and can be defined here.
        return ["Beginner", "Intermediate", "Expert"]
