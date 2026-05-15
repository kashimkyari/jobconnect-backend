from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional

from app.models.user import User
from app.models.notification import NotificationCategory
from app.services.profile_view_service import ProfileViewService
from app.services.notification_service import NotificationService
from app.schemas.notification import NotificationCreate
from app.database import get_db
from app.utils.security import get_current_user, TokenData
from fastapi import BackgroundTasks

router = APIRouter(prefix="/users", tags=["Profile Views"])


class ProfileViewerSchema(BaseModel):
    id: int
    name: str
    avatar_url: Optional[str] = None
    rating: float
    viewed_at: str

    class Config:
        from_attributes = True


class ProfileViewCountSchema(BaseModel):
    total_views: int
    this_month_views: int

    class Config:
        from_attributes = True


@router.post("/me/profile-viewed")
async def record_profile_view(
    user_id: int = Query(..., description="ID of the user whose profile is being viewed"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Record that current user viewed another user's profile.
    This creates an activity record for the profile owner and sends a notification.
    """
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot record view of your own profile"
        )
    
    profile_view_service = ProfileViewService(db)
    view = await profile_view_service.record_profile_view(user_id=user_id, viewer_id=current_user.id)
    
    # Notify the user whose profile was viewed
    if view:
        notification_service = NotificationService(db)
        await notification_service.create_notification(
            NotificationCreate(
                user_id=user_id,
                title="Profile View",
                message=f"{current_user.first_name} {current_user.last_name} viewed your profile.",
                category=NotificationCategory.PROFILE_VIEW
            )
        )
    
    return {
        "status": "success",
        "message": "Profile view recorded"
    }


@router.get("/me/profile-views/count", response_model=ProfileViewCountSchema)
async def get_profile_view_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get profile view count for current user
    """
    profile_view_service = ProfileViewService(db)
    total_views = await profile_view_service.get_profile_view_count(current_user.id)
    
    # For this month count, would need to filter by date - simplified for now
    this_month_views = total_views  # Placeholder
    
    return {
        "total_views": total_views,
        "this_month_views": this_month_views
    }


@router.get("/me/profile-viewers", response_model=List[ProfileViewerSchema])
async def get_recent_profile_viewers(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of recent profile viewers
    """
    profile_view_service = ProfileViewService(db)
    viewers = await profile_view_service.get_recent_profile_viewers(current_user.id, limit=limit)
    
    return viewers
