from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.profile_view import ProfileView
from app.models.user import User
from app.schemas.employer_dashboard import ActivityType
from app.models.recent_activity import RecentActivity
from datetime import datetime


class ProfileViewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_profile_view(self, user_id: int, viewer_id: int) -> ProfileView:
        """Record a profile view"""
        profile_view = ProfileView(user_id=user_id, viewer_id=viewer_id)
        self.db.add(profile_view)
        
        # Also create an activity record for the profile owner
        viewer = await self.db.get(User, viewer_id)
        viewer_name = f"{viewer.first_name} {viewer.last_name}" if viewer else "Someone"
        
        activity = RecentActivity(
            user_id=user_id,
            activity_type=ActivityType.PROFILE_VIEW,
            description=f"{viewer_name} viewed your profile",
            activity_data={
                "action_label": "Profile Viewed",
                "target_id": viewer_id,
                "target_name": viewer_name,
                "target_image_url": viewer.avatar_url if viewer else None
            },
            timestamp=datetime.utcnow()
        )
        self.db.add(activity)
        
        await self.db.commit()
        await self.db.refresh(profile_view)
        return profile_view

    async def get_profile_view_count(self, user_id: int) -> int:
        """Get total profile views for a user"""
        stmt = select(func.count(ProfileView.id)).where(
            ProfileView.user_id == user_id
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def get_recent_profile_viewers(self, user_id: int, limit: int = 10) -> list:
        """Get recent profile viewers"""
        stmt = select(ProfileView).where(
            ProfileView.user_id == user_id
        ).order_by(ProfileView.viewed_at.desc()).limit(limit)
        
        result = await self.db.execute(stmt)
        views = result.scalars().all()
        
        viewers = []
        for view in views:
            viewer = await self.db.get(User, view.viewer_id)
            if viewer:
                viewers.append({
                    "id": viewer.id,
                    "name": f"{viewer.first_name} {viewer.last_name}",
                    "avatar_url": viewer.avatar_url,
                    "rating": viewer.reputation_score,
                    "viewed_at": view.viewed_at
                })
        
        return viewers
