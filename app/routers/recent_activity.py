from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.schemas.recent_activity import RecentActivityOut
from app.services.recent_activity_service import RecentActivityService
from app.services.auth_service import get_current_user, is_admin
from app.models.user import User

router = APIRouter()

@router.get("/users/me/recent-activity", response_model=List[RecentActivityOut])
async def read_user_recent_activities(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    activity_service = RecentActivityService(db)
    activities = await activity_service.get_activities_for_user(user_id=current_user.id, skip=skip, limit=limit)
    return activities

@router.get("/recent-activity", response_model=List[RecentActivityOut], dependencies=[Depends(is_admin)])
async def read_general_recent_activities(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    activity_service = RecentActivityService(db)
    activities = await activity_service.get_all_activities(skip=skip, limit=limit)
    return activities
