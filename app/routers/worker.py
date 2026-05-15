from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.user import UserProfile, WorkerProfileUpdate
from app.services.worker_service import WorkerService
from app.dependencies.worker import get_current_worker
from app.utils.security import get_current_user
from app.models.user import User
from pydantic import BaseModel

router = APIRouter()

class ProfileCompletion(BaseModel):
    completion_percentage: int
    fields_completed: list[str]
    fields_remaining: list[str]

@router.get("/profile", response_model=UserProfile)
async def get_user_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_worker)
):
    """
    Retrieve the profile of the currently authenticated worker.
    """
    return await WorkerService.get_user_profile(db, user_id=current_user.id)

@router.put("/profile", response_model=UserProfile)
async def update_user_profile(
    profile_data: WorkerProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_worker)
):
    """
    Update the profile of the currently authenticated worker.
    """
    return await WorkerService.update_user_profile(db, user_id=current_user.id, profile_data=profile_data)

@router.get("/completion", response_model=ProfileCompletion)
async def get_profile_completion(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_worker)
):
    """
    Get profile completion status for the currently authenticated worker.
    """
    return await WorkerService.get_profile_completion_status(db, user_id=current_user.id)
