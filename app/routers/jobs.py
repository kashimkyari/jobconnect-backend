from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Union, Optional
from datetime import datetime, timedelta
import logging
import base64

from ..models.user import User, UserRole
from ..models.job import JobStatus, JobLocationType
from ..models.job_application import ApplicationStatus
from ..models.payment import PaymentStatus
from ..schemas.job import (
    JobCreate,
    JobUpdate,
    JobInDB,
    ActiveJob,
    EmployerJobDetail,
    WorkerJobDetail,
)
from ..schemas.job_application import ContractResponse
from ..schemas.job_with_applications import JobWithApplications
from ..schemas.job_with_application_count import JobWithApplicationCount
from ..schemas.applicant import ApplicantProfile
from ..schemas.job_application import (
    JobApplicationCreate,
    JobApplicationInDB,
    JobApplicationStatusUpdate,
    HiringConfirmationRequest,
)
from ..schemas.dispute import DisputeCreate, DisputeInDB
from ..services.job_service import JobService
from ..services.dispute_service import DisputeService
from ..services.profile_view_service import ProfileViewService
from ..database import get_db
from ..utils.security import get_current_user, check_permissions, TokenData
from ..utils.logging import StructuredLogger

router = APIRouter(tags=["Jobs"])
logger = StructuredLogger(__name__)


def extract_request_id(request: Request) -> Optional[str]:
    """
    Extract idempotency/request ID from request headers.
    Checks for: X-Request-ID, Idempotency-Key, X-Idempotency-Key (in that order)
    """
    return (
        request.headers.get('X-Request-ID') or
        request.headers.get('Idempotency-Key') or
        request.headers.get('X-Idempotency-Key')
    )



@router.post("/{job_id}/view", status_code=201)
async def record_job_view(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Record a view for a job by the current user. This records a view on the job poster's profile.
    """
    job_service = JobService(db)
    job = await job_service.get_job(job_id, current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.employer_id != current_user.id:
        service = ProfileViewService(db)
        await service.record_profile_view(
            user_id=job.employer_id,
            viewer_id=current_user.id,
        )
    
    return {"message": "Job view recorded successfully"}

@router.post("/", response_model=JobInDB, status_code=status.HTTP_201_CREATED)
async def create_job(
    request: Request,
    job: JobCreate,
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db)
):
    job_service = JobService(db)

    new_job = await job_service.create_job(
        job,
        current_user.id,
        request_id=extract_request_id(request),
    )
    return new_job

@router.get("/", response_model=List[JobInDB])
async def list_jobs(
    status: JobStatus | None = None,
    location_type: JobLocationType | None = None,
    category: str | None = None,
    location: str | None = None,
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.WORKER, UserRole.EMPLOYER))
):
    try:
        job_service = JobService(db)
        jobs = await job_service.get_jobs(
            user_id=current_user.id,
            status=status,
            location_type=location_type,
            category=category,
            location=location,
            skip=skip,
            limit=limit
        )
        return jobs
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Jobs] Error in list_jobs: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )

@router.get("/worker/available", response_model=List[JobInDB])
async def list_available_jobs_for_worker(
    skip: int = 0,
    limit: int = 100,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_km: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.WORKER))
):
    """
    Endpoint for workers to get available jobs.
    
    Optionally filters by location if latitude and longitude are provided.
    """
    try:
        job_service = JobService(db)
        
        # If location is provided, use location-based filtering
        if latitude is not None and longitude is not None:
            from app.services.location_service import LocationService
            location_service = LocationService(db)
            
            # Get nearby jobs with distance
            jobs_with_distance = await location_service.get_nearby_jobs_with_distance(
                worker_latitude=latitude,
                worker_longitude=longitude,
                radius_km=radius_km,
                limit=limit + skip  # Get extra to account for skip
            )
            
            # Apply skip and limit
            jobs_with_distance = jobs_with_distance[skip:skip+limit]
            
            # Convert to response with distance fields
            result = []
            for item in jobs_with_distance:
                job = item["job"]
                job_dict = job.__dict__.copy()
                job_dict["distance_km"] = item["distance_km"]
                job_dict["distance_display"] = item["distance_display"]
                result.append(JobInDB.model_validate(job_dict))
            
            return result
        else:
            # Fallback to original behavior without location filtering
            jobs = await job_service.get_available_jobs_for_worker(
                skip=skip,
                limit=limit
            )
            return jobs
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching available jobs"
        )

@router.get("/worker/recommended", response_model=List[JobInDB])
async def get_recommended_jobs_for_worker(
    skip: int = 0,
    limit: int = 10,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_km: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.WORKER))
):
    """
    Get recommended jobs for a worker based on their location and profile.
    
    If latitude and longitude are provided, filters jobs within the radius.
    Falls back to all available jobs if location not provided.
    """
    try:
        job_service = JobService(db)
        
        # Use location if provided
        if latitude is not None and longitude is not None:
            from app.services.location_service import LocationService
            location_service = LocationService(db)
            
            # Get nearby jobs with distance, ordered by relevance
            jobs_with_distance = await location_service.get_nearby_jobs_with_distance(
                worker_latitude=latitude,
                worker_longitude=longitude,
                radius_km=radius_km,
                limit=limit + skip  # Get extra to account for skip
            )
            
            # Apply skip and limit
            jobs_with_distance = jobs_with_distance[skip:skip+limit]
            
            # Convert to response with distance fields
            result = []
            for item in jobs_with_distance:
                job = item["job"]
                job_dict = job.__dict__.copy()
                job_dict["distance_km"] = item["distance_km"]
                job_dict["distance_display"] = item["distance_display"]
                result.append(JobInDB.model_validate(job_dict))
            
            return result
        else:
            # Fallback: get available jobs without location filtering
            jobs = await job_service.get_available_jobs_for_worker(
                skip=skip,
                limit=limit
            )
            return jobs
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching recommended jobs"
        )

@router.get("/my-jobs", response_model=Union[List[JobWithApplications], List[JobInDB]])
async def get_my_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get employer's posted jobs or worker's accepted jobs with comprehensive details"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    try:
        job_service = JobService(db)
        if current_user.role == UserRole.EMPLOYER:
            jobs = await job_service.get_employer_jobs(current_user.id)
        elif current_user.role == UserRole.WORKER:
            jobs = await job_service.get_worker_jobs(current_user.id)
        else:
            jobs = []
        return jobs
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve jobs: {str(e)}"
        )

@router.get("/my-applications", response_model=List[JobApplicationInDB])
async def get_my_applications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.WORKER))
):
    try:
        job_service = JobService(db)
        applications = await job_service.get_worker_applications(current_user.id)
        return applications
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Jobs] Error in get_my_applications: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve jobs: {str(e)}"
        )

@router.get("/my-active-jobs", response_model=List[ActiveJob])
async def get_my_active_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get active jobs for the current user."""
    try:
        job_service = JobService(db)
        if current_user.role == UserRole.EMPLOYER:
            jobs = await job_service.get_employer_active_jobs(current_user.id)
        elif current_user.role == UserRole.WORKER:
            jobs = await job_service.get_worker_active_jobs(current_user.id)
        else:
            jobs = []
        return jobs
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve active jobs: {str(e)}"
        )

@router.get("/{job_id}", response_model=Union[JobWithApplications, JobWithApplicationCount])
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        job_service = JobService(db)
        job = await job_service.get_job(job_id, current_user.id if current_user else None)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )

        if job.status == JobStatus.IN_PROGRESS:
            if current_user and current_user.role == UserRole.EMPLOYER and job.employer_id == current_user.id:
                pass
            elif current_user and current_user.role == UserRole.WORKER:
                application = await job_service.get_accepted_application(job_id)
                if not application or application.worker_id != current_user.id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You are not authorized to view this job"
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not authorized to view this job"
                )

        if current_user and current_user.role == UserRole.WORKER:
            # job_service.get_job() returns JobWithApplications; convert safely by
            # deriving application_count explicitly to satisfy JobWithApplicationCount.
            job_payload = job.model_dump(exclude={"applications"})
            job_payload["application_count"] = len(job.applications or [])
            return JobWithApplicationCount.model_validate(job_payload)

        return JobWithApplications.from_orm(job)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve job: {str(e)}"
        )

@router.put("/{job_id}", response_model=JobInDB)
async def update_job(
    job_id: int,
    job_update: JobUpdate,
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db)
):
    job_service = JobService(db)
    updated_job = await job_service.update_job(job_id, job_update, current_user.id)
    if not updated_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    return updated_job

@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: int,
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db)
):
    job_service = JobService(db)
    success = await job_service.delete_job(job_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )

@router.post("/{job_id}/apply", response_model=JobApplicationInDB, status_code=status.HTTP_201_CREATED)
async def apply_to_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    application: JobApplicationCreate,
    current_user: User = Depends(check_permissions(UserRole.WORKER)),
    db: AsyncSession = Depends(get_db)
):
    job_service = JobService(db)
    try:
        # Create the application - this will handle job existence check internally
        new_application = await job_service.create_application(
            job_id, application, current_user.id
        )

        return new_application
    except HTTPException as e:
        # Re-raise HTTP exceptions as is
        raise e
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Handle unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while processing your application: {e}"
        )

@router.put(
    "/{job_id}/applications/{application_id}",
    response_model=JobApplicationInDB
)
async def update_application_status(
    job_id: int,
    application_id: int,
    status_update: JobApplicationStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    logger.info(
        "Updating application status",
        job_id=job_id,
        application_id=application_id,
        user_id=current_user.id,
        role=current_user.role,
        payload=status_update.dict()
    )
    try:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        job_service = JobService(db)

        # Get the application to check existence and ownership before updating
        application = await job_service.get_application(application_id)
        if not application or application.job_id != job_id:
            logger.warning(
                "Application not found or job ID mismatch",
                application_id=application_id,
                job_id=job_id
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )

        status_enum = ApplicationStatus(status_update.status)

        if current_user.role == UserRole.WORKER:
            if status_enum not in [ApplicationStatus.WITHDRAWN, ApplicationStatus.OFFER_ACCEPTED, ApplicationStatus.OFFER_DECLINED]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Workers can only withdraw, accept, or decline applications"
                )
            updated_application = await job_service.update_application_status(
                job_id, application_id, status_enum, worker_id=current_user.id
            )
        elif current_user.role == UserRole.EMPLOYER:
            updated_application = await job_service.update_application_status(
                job_id, application_id, status_enum, employer_id=current_user.id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action"
            )

        logger.info("Successfully updated application status", application_id=application_id)
        return updated_application
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update application status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update application status: {str(e)}"
        )

@router.put("/{job_id}/complete", response_model=JobInDB)
async def mark_job_as_complete(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: str = None,
):
    job_service = JobService(db)
    completed_job = await job_service.mark_job_as_complete(job_id, current_user, request_id)
    return completed_job


@router.put("/{job_id}/publish", response_model=JobInDB)
async def publish_job(
    job_id: int,
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db),
    request_id: str = None  # Optional idempotency key from header
):
    """
    Publish a job from DRAFT to OPEN status.
    Only the job owner (employer) can publish.
    """
    job_service = JobService(db)
    job = await job_service.publish_job(job_id, current_user.id, request_id=request_id)
    return job


@router.put("/{job_id}/unpublish", response_model=JobInDB)
async def unpublish_job(
    job_id: int,
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db),
    request_id: str = None
):
    """
    Unpublish a job from OPEN back to DRAFT status.
    Only works if no workers have been hired yet.
    """
    job_service = JobService(db)
    job = await job_service.unpublish_job(job_id, current_user.id, request_id=request_id)
    return job


@router.put("/{job_id}/archive", response_model=JobInDB)
async def archive_job(
    job_id: int,
    request: Request,
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db),
):
    """
    Archive a job (hide from listings).
    Can be archived from OPEN or IN_PROGRESS states.
    Applications and contracts remain intact.
    
    Supports idempotency via X-Request-ID, Idempotency-Key, or X-Idempotency-Key headers.
    """
    request_id = extract_request_id(request)
    
    logger.info(
        "Archive job request",
        job_id=job_id,
        employer_id=current_user.id,
        request_id=request_id
    )
    
    try:
        job_service = JobService(db)
        job = await job_service.archive_job(job_id, current_user.id, request_id=request_id)
        
        logger.info(
            "Job archived successfully",
            job_id=job_id,
            employer_id=current_user.id,
            request_id=request_id
        )
        return job
    except HTTPException:
        logger.warning(
            "Archive job failed",
            job_id=job_id,
            employer_id=current_user.id,
            request_id=request_id
        )
        raise
    except Exception as e:
        logger.error(
            "Archive job error",
            job_id=job_id,
            employer_id=current_user.id,
            request_id=request_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to archive job: {str(e)}"
        )


@router.put("/{job_id}/unarchive", response_model=JobInDB)
async def unarchive_job(
    job_id: int,
    request: Request,
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db),
):
    """
    Unarchive a job (restore to visible state).
    Restores to the last publishable state.
    
    Supports idempotency via X-Request-ID, Idempotency-Key, or X-Idempotency-Key headers.
    """
    request_id = extract_request_id(request)
    
    logger.info(
        "Unarchive job request",
        job_id=job_id,
        employer_id=current_user.id,
        request_id=request_id
    )
    
    try:
        job_service = JobService(db)
        job = await job_service.unarchive_job(job_id, current_user.id, request_id=request_id)
        
        logger.info(
            "Job unarchived successfully",
            job_id=job_id,
            employer_id=current_user.id,
            request_id=request_id
        )
        return job
    except HTTPException:
        logger.warning(
            "Unarchive job failed",
            job_id=job_id,
            employer_id=current_user.id,
            request_id=request_id
        )
        raise
    except Exception as e:
        logger.error(
            "Unarchive job error",
            job_id=job_id,
            employer_id=current_user.id,
            request_id=request_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unarchive job: {str(e)}"
        )


# Enhanced Job Detail APIs for Mobile

@router.get("/{job_id}/enhanced-details")
async def get_enhanced_job_details(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive job details with applications and applicant info for employers"""
    job_service = JobService(db)
    worker_id = current_user.id if current_user and current_user.role == UserRole.WORKER else None
    job = await job_service.get_job(job_id, user_id=current_user.id if current_user else None, worker_id=worker_id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    # Authorization checks
    if current_user and current_user.role == UserRole.EMPLOYER and job.employer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this job's details"
        )
    
    return job

@router.post("/{job_id}/withdraw", response_model=JobApplicationInDB)
async def withdraw_application(
    job_id: int,
    current_user: User = Depends(check_permissions(UserRole.WORKER)),
    db: AsyncSession = Depends(get_db)
):
    job_service = JobService(db)
    return await job_service.withdraw_application(job_id, current_user.id)

@router.post("/{job_id}/boost-application", response_model=JobApplicationInDB)
async def boost_application(
    job_id: int,
    current_user: User = Depends(check_permissions(UserRole.WORKER)),
    db: AsyncSession = Depends(get_db)
):
    job_service = JobService(db)
    return await job_service.boost_application(job_id, current_user.id)

@router.get("/{job_id}/application-status", response_model=Optional[JobApplicationInDB])
async def get_application_status(
    job_id: int,
    current_user: User = Depends(check_permissions(UserRole.WORKER)),
    db: AsyncSession = Depends(get_db)
):
    job_service = JobService(db)
    return await job_service.get_worker_application(job_id, current_user.id)


@router.get("/{job_id}/applications-summary")
async def get_job_applications_summary(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """Get summary of all applications for a job with applicant profiles"""
    from sqlalchemy import select
    
    job_service = JobService(db)
    job = await job_service.get_job(job_id, current_user.id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    if job.employer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view these applications"
        )
    
    # Get recent applicants (most recent first, limit to 5)
    recent_applicants = []
    sorted_apps = sorted(
        [a for a in (job.applications or []) if a.worker],
        key=lambda x: x.created_at or datetime.utcnow(),
        reverse=True
    )[:5]
    
    for app in sorted_apps:
        if app.worker:  # Safety check
            recent_applicants.append({
                "id": app.worker_id,
                "name": f"{app.worker.first_name or 'Unknown'} {app.worker.last_name or ''}".strip(),
                "title": app.worker.bio or "N/A",
                "avatar": app.worker.avatar_url or None,
                "status": app.status.value if app.status else "pending"
            })
    
    # Count applications by status
    applications = job.applications or []
    shortlisted_count = len([a for a in applications if a.status == ApplicationStatus.REVIEWING])
    
    return {
        "total_applicants": len(applications),
        "shortlisted_count": shortlisted_count,
        "recent_applicants": recent_applicants
    }


@router.get("/{job_id}/applicant/{applicant_id}", response_model=ApplicantProfile)
async def get_applicant_profile(
    job_id: int,
    applicant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """Get detailed applicant profile for a specific job application"""
    from sqlalchemy import select
    
    job_service = JobService(db)
    job = await job_service.get_job(job_id, current_user.id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    if job.employer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view this information"
        )
    
    # Get the application with worker details
    application = await job_service.get_application_by_job_and_worker(job_id, applicant_id)
    
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    worker = application.worker
    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worker profile not found"
        )
    
    return {
        "application_id": application.id,
        "status": application.status.value if application.status else "pending",
        "applied_at": application.created_at,
        "proposed_budget": float(application.proposed_budget) if application.proposed_budget else 0.0,
        "cover_letter": application.cover_letter or "",
        "worker": worker,
        "job": job
    }


@router.post("/{job_id}/applicant/{applicant_id}/shortlist")
async def shortlist_applicant(
    job_id: int,
    applicant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """Mark an applicant as shortlisted"""
    try:
        job_service = JobService(db)
        job = await job_service.get_job(job_id, current_user.id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        if job.employer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to shortlist applicants for this job"
            )
        
        application = await job_service.get_application(applicant_id)
        if not application or application.job_id != job_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        # Update application status to REVIEWING (shortlist)
        updated_app = await job_service.update_application_status(
            job_id, applicant_id, ApplicationStatus.REVIEWING, employer_id=current_user.id
        )
        
        return {
            "success": True,
            "message": "Applicant shortlisted successfully",
            "application_id": updated_app.id,
            "status": updated_app.status.value if updated_app.status else "reviewing"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to shortlist applicant: {str(e)}"
        )


@router.post("/{job_id}/applicant/{applicant_id}/reject")
async def reject_applicant(
    job_id: int,
    applicant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """Reject an applicant"""
    try:
        job_service = JobService(db)
        job = await job_service.get_job(job_id, current_user.id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        if job.employer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to reject applicants for this job"
            )
        
        application = await job_service.get_application(applicant_id)
        if not application or application.job_id != job_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        # Update application status to REJECTED
        updated_app = await job_service.update_application_status(
            job_id, applicant_id, ApplicationStatus.REJECTED, employer_id=current_user.id
        )
        
        return {
            "success": True,
            "message": "Application rejected successfully",
            "application_id": updated_app.id,
            "status": updated_app.status.value if updated_app.status else "rejected"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reject applicant: {str(e)}"
        )


@router.get("/{job_id}/analytics")
async def get_job_analytics(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """Get analytics and performance metrics for a job posting"""
    try:
        job_service = JobService(db)
        job = await job_service.get_job(job_id, current_user.id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        if job.employer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view these analytics"
            )
        
        # Calculate analytics from applications
        applications = job.applications or []
        total_applicants = len(applications)
        reviewing_count = len([a for a in applications if a.status == ApplicationStatus.REVIEWING])
        rejected_count = len([a for a in applications if a.status == ApplicationStatus.REJECTED])
        selected_count = len([a for a in applications if a.status == ApplicationStatus.ACCEPTED])
        
        # Get today's applications count
        today = datetime.utcnow().date()
        today_applications = len([
            a for a in applications 
            if a.created_at and a.created_at.date() == today
        ])
        
        return {
            "job_id": job.id,
            "job_title": job.title or "Untitled",
            "total_applicants": total_applicants,
            "total_views": getattr(job, 'views_count', 0) or 0,
            "matched_applicants": reviewing_count,
            "today_applications": today_applications,
            "shortlisted_count": reviewing_count,
            "interviews_count": selected_count,
            "rejected_count": rejected_count,
            "posted_at": job.created_at.isoformat() if job.created_at else None,
            "status": job.status.value if job.status else "open"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving job analytics: {str(e)}"
        )


@router.post("/{job_id}/boost")
async def boost_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Boost a job to increase visibility in search results.
    
    Cost: ₦999 for 7 days
    Effect: Job appears first in relevant search results
    
    Returns boost details and confirmation
    """
    try:
        job_service = JobService(db)
        result = await job_service.boost_job(job_id, current_user.id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to boost job: {str(e)}"
        )


@router.post("/{job_id}/share")
async def share_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """Generate a shareable link for a job posting"""
    try:
        job_service = JobService(db)
        job = await job_service.get_job(job_id, current_user.id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        if job.employer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to share this job"
            )
        
        # Generate share code
        share_code = base64.b64encode(f"JOB_{job.id}_{current_user.id}".encode()).decode()[:12]
        
        return {
            "success": True,
            "share_url": f"https://jobconnect.app/jobs/{job_id}?share={share_code}",
            "share_code": f"JOB_{job_id}",
            "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
            "message": "Share link generated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate share link: {str(e)}"
        )

@router.get("/{job_id}/applicants", response_model=List[JobApplicationInDB])
async def get_job_applicants(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """Get all applicants for a specific job."""
    try:
        job_service = JobService(db)
        
        # First, verify that the job exists and belongs to the current employer
        job = await job_service.get_job(job_id, current_user.id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        if job.employer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view applicants for this job"
            )

        # Fetch the applicants
        applicants = await job_service.get_applicants_for_job(job_id)
        return applicants
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve applicants: {str(e)}"
        )

@router.post("/{job_id}/hire/{application_id}", response_model=JobApplicationInDB)
async def hire_worker(
    job_id: int,
    application_id: int,
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db)
):
    job_service = JobService(db)
    return await job_service.update_application_status(
        job_id, application_id, ApplicationStatus.ACCEPTED, employer_id=current_user.id
    )

@router.post("/{job_id}/confirm-hire/{application_id}", status_code=status.HTTP_200_OK)
async def confirm_hire_with_details(
    job_id: int,
    application_id: int,
    confirmation: HiringConfirmationRequest,
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db)
):
    """
    Confirm hiring a worker with optional price negotiation.
    - action: 'accept' to accept worker's proposed price
    - action: 'negotiate' to counter-offer with different price
    """
    job_service = JobService(db)
    result = await job_service.confirm_hire_with_negotiation(
        job_id=job_id,
        application_id=application_id,
        negotiated_price=confirmation.negotiated_price,
        contract_details=confirmation.contract_details,
        action=confirmation.action,
        employer_id=current_user.id
    )
    return result

@router.post("/{job_id}/dispute", response_model=DisputeInDB)
async def create_dispute(
    job_id: int,
    dispute: DisputeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a dispute for a job."""
    try:
        dispute_service = DisputeService(db)
        new_dispute = await dispute_service.create_dispute(
            job_id=job_id,
            dispute_create=dispute,
            user_id=current_user.id
        )
        return new_dispute
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create dispute: {str(e)}"
        )

@router.post("/{job_id}/cancel", response_model=JobInDB)
async def cancel_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel a job."""
    try:
        job_service = JobService(db)
        cancelled_job = await job_service.cancel_job(job_id, current_user)
        return cancelled_job
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel job: {str(e)}"
        )

@router.put("/{job_id}/approve-completion", response_model=JobInDB)
async def approve_job_completion(
    job_id: int,
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db)
):
    """Employer approves job completion."""
    job_service = JobService(db)
    updated_job = await job_service.approve_completion(job_id, current_user.id)
    return updated_job

@router.put("/{job_id}/applications/{app_id}", response_model=JobApplicationInDB)
async def update_application_status(
    job_id: int,
    app_id: int,
    status_update: JobApplicationStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update application status (accept/reject/withdraw)."""
    job_service = JobService(db)
    updated_app = await job_service.update_application_status(
        job_id, app_id, status_update.status, current_user.id
    )
    return updated_app


@router.get("/employer/{job_id}", response_model=Union[EmployerJobDetail, WorkerJobDetail])
async def get_employer_job_detail(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed job information for the employer."""
    job_service = JobService(db)
    if current_user.role == UserRole.EMPLOYER:
        job = await job_service.get_job_for_employer(job_id, current_user.id)
    elif current_user.role == UserRole.WORKER:
        job = await job_service.get_job_for_worker(job_id, current_user.id)
    else:
        raise HTTPException(status_code=403, detail="Operation not permitted")

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/worker/{job_id}", response_model=WorkerJobDetail)
async def get_worker_job_detail(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.WORKER)),
):
    """Get detailed job information for the worker."""
    job_service = JobService(db)
    job = await job_service.get_job_for_worker(job_id, current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/nearby/list", response_model=List[dict])
async def get_nearby_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.WORKER)),
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_km: Optional[int] = None,
    city: Optional[str] = None,
    category_id: Optional[int] = None,
    experience_level: Optional[str] = None,
    limit: int = 50,
):
    """Get jobs nearby the worker's location.
    
    Query parameters:
    - latitude: Worker's latitude (uses current user's location if not provided)
    - longitude: Worker's longitude (uses current user's location if not provided)
    - city: Optional city name for reference
    - radius_km: Search radius in kilometers (uses user's preference if not provided)
    - category_id: Optional category filter
    - experience_level: Optional experience level filter
    - limit: Maximum results (default 50, max 200)
    
    Uses location coordinates to find nearby open jobs within the specified radius.
    """
    from ..services.location_service import LocationService
    from ..models.user import UserRole
    
    # Validate limit
    limit = min(int(limit), 200) if limit else 50
    
    # Use provided location or fall back to user's stored location
    if latitude is None or longitude is None:
        if current_user.latitude is None or current_user.longitude is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location not provided. Please provide latitude and longitude or set your location in profile."
            )
        latitude = current_user.latitude
        longitude = current_user.longitude
    
    # Validate coordinates
    try:
        latitude = float(latitude)
        longitude = float(longitude)
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise ValueError("Invalid coordinates")
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid latitude/longitude values"
        )
    
    try:
        location_service = LocationService(db)
        radius_km = location_service.resolve_search_radius_km(user=current_user, radius_km=radius_km)
        logger = logging.getLogger(__name__)
        logger.info(f"[get_nearby_jobs] Worker {current_user.id} searching at ({latitude}, {longitude}), radius={radius_km}km")
        nearby_jobs = await location_service.get_nearby_jobs(
            worker_latitude=latitude,
            worker_longitude=longitude,
            radius_km=radius_km,
            category_id=category_id,
            experience_level=experience_level,
            limit=limit
        )
        
        logger.info(f"[get_nearby_jobs] Found {len(nearby_jobs)} jobs for worker {current_user.id}")
    except Exception as e:
        logger.error(f"[get_nearby_jobs] Error fetching nearby jobs: {str(e)}")
        return []
    
    # Convert to response format with distance and comprehensive employer info
    result = []
    for job, distance in nearby_jobs:
        try:
            # Convert ORM object to shallow dict without triggering lazy-load IO
            job_data = job.__dict__.copy()
            job_data.pop('_sa_instance_state', None)

            # distance may be None for remote jobs
            if distance is None:
                job_data["distance_km"] = None
                job_data["distance_display"] = "Remote"
            else:
                job_data["distance_km"] = round(distance, 2)
                try:
                    job_data["distance_display"] = location_service.format_distance(distance)
                except Exception:
                    job_data["distance_display"] = f"{round(distance,2)} km"

            # Add employer info safely (avoid triggering async lazy-loads)
            try:
                emp = getattr(job, 'employer', None)
                if emp is not None:
                    first_name = getattr(emp, 'first_name', '') or ''
                    last_name = getattr(emp, 'last_name', '') or ''
                    employer_name = f"{first_name} {last_name}".strip() or "Employer"

                    job_data["employer_name"] = employer_name
                    job_data["employer_rating"] = float(getattr(emp, 'reputation_score', 4.7) or 4.7)
                    job_data["employer"] = {
                        "id": getattr(emp, 'id', None),
                        "first_name": first_name,
                        "last_name": last_name,
                        "full_name": employer_name,
                        "avatar_url": getattr(emp, 'avatar_url', None),
                        "rating": float(getattr(emp, 'reputation_score', 4.7) or 4.7),
                    }
                else:
                    job_data["employer_name"] = "Employer"
                    job_data["employer_rating"] = 4.7
            except Exception as e:
                logger.error(f"Error adding employer info for job {getattr(job,'id',None)}: {str(e)}")
                job_data["employer_name"] = "Employer"
                job_data["employer_rating"] = 4.7

            # Map payment type to values frontend expects
            try:
                if getattr(job, 'payment_type', None):
                    payment_type_value = job.payment_type.value if hasattr(job.payment_type, 'value') else str(job.payment_type)
                    if payment_type_value == "hourly_rate":
                        job_data["hourly_rate"] = float(getattr(job, 'hourly_rate', 0) or 0)
                        job_data["rate_per_hour"] = float(getattr(job, 'hourly_rate', 0) or 0)
                    else:
                        job_data["budget"] = float(getattr(job, 'job_price', 0) or 0)
                        job_data["job_price"] = float(getattr(job, 'job_price', 0) or 0)
            except Exception:
                pass

            # Add is_urgent flag (derived from boost status)
            job_data["is_urgent"] = bool(getattr(job, 'boost_active', False))
            job_data["urgent"] = bool(getattr(job, 'boost_active', False))

            # Ensure category_name is present
            if not job_data.get("category_name") and getattr(job, 'category_id', None):
                job_data["category_name"] = str(getattr(job, 'category_id'))

            result.append(job_data)
        except Exception as e:
            # Log the error but continue processing
            try:
                logger.error(f"Error processing job {getattr(job,'id',None)}: {str(e)}")
            except Exception:
                logger.error(f"Error processing job (unknown id): {str(e)}")
            continue
    
    return result
