from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..database import get_db
from ..services.meta_service import MetaService
from ..models.job_application import ApplicationStatus

router = APIRouter(prefix="/meta", tags=["Meta"])

@router.get("/services", response_model=List[str])
async def get_services(db: AsyncSession = Depends(get_db)):
    """
    Get a list of all unique service names.
    """
    meta_service = MetaService(db)
    return await meta_service.get_unique_services()

@router.get("/categories", response_model=List[str])
async def get_categories(db: AsyncSession = Depends(get_db)):
    """
    Get a list of all unique service categories.
    """
    meta_service = MetaService(db)
    return await meta_service.get_unique_categories()

@router.get("/skills", response_model=List[str])
async def get_skills(db: AsyncSession = Depends(get_db)):
    """
    Get a list of the most common skills.
    """
    meta_service = MetaService(db)
    return await meta_service.get_common_skills()

@router.get("/locations", response_model=List[str])
async def get_locations(db: AsyncSession = Depends(get_db)):
    """
    Get a list of distinct worker locations.
    """
    meta_service = MetaService(db)
    return await meta_service.get_distinct_locations()

@router.get("/experience-levels", response_model=List[str])
async def get_experience_levels(db: AsyncSession = Depends(get_db)):
    """
    Get a list of possible experience levels.
    """
    meta_service = MetaService(db)
    return await meta_service.get_experience_levels()

@router.get("/application-statuses", response_model=List[str])
async def get_application_statuses():
    """
    Get a list of all possible application statuses.
    """
    return [status.value for status in ApplicationStatus]
