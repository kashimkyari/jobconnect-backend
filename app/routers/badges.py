from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from app.models.user import User
from app.services.badge_service import BadgeService
from app.database import get_db
from app.utils.security import get_current_user
from app.schemas.badge import Badge

router = APIRouter()

@router.get("/", response_model=List[Badge])
async def get_all_badges(
    db: AsyncSession = Depends(get_db),
):
    """Get all available badges."""
    badge_service = BadgeService(db)
    return await badge_service.get_all_badges()

@router.get("/my-badges", response_model=List[Badge])
async def get_my_badges(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all badges earned by the current user."""
    badge_service = BadgeService(db)
    return await badge_service.get_user_badges(current_user.id)

@router.get("/top-rated/status", response_model=Dict[str, Any])
async def check_top_rated_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if the user has or qualifies for the 'Top Rated' badge.
    Returns detailed status including current reputation score, required score, and gap.
    """
    badge_service = BadgeService(db)
    status = await badge_service.check_top_rated_badge_status(current_user.id)
    return status

@router.get("/progress", response_model=List[Dict[str, Any]])
async def get_badge_progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get progress toward earning all badges.
    Useful for displaying badge progress bars or achievement milestones in the UI.
    """
    badge_service = BadgeService(db)
    progress = await badge_service.get_badge_progress(current_user.id)
    return progress
