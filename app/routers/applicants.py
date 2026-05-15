from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.database import get_db
from app.services.job_service import JobService
from app.schemas.applicant import Applicant
from app.schemas.job_application import JobApplicationInDB
from app.models.user import User, UserRole
from app.utils.security import check_permissions, get_current_user
from app.models.job_application import ApplicationStatus

router = APIRouter()

@router.get("/jobs/{job_id}/applicants", response_model=List[Applicant])
async def get_job_applicants(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    job_service = JobService(db)
    job = await job_service.get_job(job_id, current_user.id)
    if not job or job.employer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view applicants for this job")
    
    applicants = await job_service.get_applicants_by_job_id(job_id, sort_by_boosted=True)
    return applicants

@router.get("/jobs/{job_id}/applicants/{application_id}", response_model=Applicant)
async def get_applicant(
    job_id: int,
    application_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    job_service = JobService(db)
    job = await job_service.get_job(job_id, current_user.id)
    if not job or job.employer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view applicants for this job")
    
    application = await job_service.get_application_by_id(application_id)
    if not application or application.job_id != job_id:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.status == ApplicationStatus.PENDING:
        await job_service.update_application_status(application_id, ApplicationStatus.REVIEWING)

    applicant = await job_service.get_applicant_by_application_id(application_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")
        
    return applicant

@router.get("/employer/applications", response_model=List[JobApplicationInDB])
async def get_employer_applications(
    status: Optional[ApplicationStatus] = None,
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db),
):
    """Get all applications for employer's jobs."""
    job_service = JobService(db)
    applications = await job_service.get_employer_applications(
        employer_id=current_user.id, status=status, skip=skip, limit=limit
    )
    return applications

@router.get("/employer/applications/stats")
async def get_employer_application_stats(
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db)
):
    """Get application statistics for employer."""
    return {
        "total_applications": int,
        "pending_applications": int,
        "accepted_applications": int,
        "rejected_applications": int,
        "total_jobs": int,
        "active_jobs": int
    }
