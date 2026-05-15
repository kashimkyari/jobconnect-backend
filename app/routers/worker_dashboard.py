from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.auth_service import get_current_worker
from app.models.user import User as UserModel
from app.schemas.worker_dashboard import WorkerHomeScreenSchema, ApplicationWithAction
from app.services.worker_dashboard_service import get_worker_dashboard_data, get_applications_with_actions
from app.services.job_service import JobService
from app.schemas.job import JobInDB
from typing import List

router = APIRouter()

@router.get("/worker/dashboard", response_model=WorkerHomeScreenSchema, tags=["Worker Dashboard"])
async def get_worker_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_worker),
):
    """
    Get all data needed for the worker's home screen.
    """
    dashboard_data = await get_worker_dashboard_data(db, current_user)
    return dashboard_data

@router.get("/worker/dashboard/active-contracts", response_model=List[JobInDB], tags=["Worker Dashboard"])
async def get_active_contracts(
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_worker),
):
    """
    Get active contracts for the current worker.
    """
    job_service = JobService(db)
    active_contracts = await job_service.get_worker_active_contracts(current_user.id)
    return active_contracts

@router.get("/worker/dashboard/applications-with-actions", response_model=List[ApplicationWithAction], tags=["Worker Dashboard"])
async def get_applications_with_actions_route(
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_worker),
):
    """
    Get recent applications with recommended actions.
    """
    applications = await get_applications_with_actions(db, current_user.id)
    return applications
