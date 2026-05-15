"""
Consolidated Dashboard Router

Provides unified endpoints for employer and worker home screens.
Single API call returns all data previously fetched via multiple parallel requests.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.database import get_db
from app.utils.security import get_current_user, check_permissions
from app.services.consolidated_dashboard_service import ConsolidatedDashboardService
from app.schemas.consolidated_dashboard import (
    EmployerConsolidatedDashboardSchema,
    WorkerConsolidatedDashboardSchema,
)

router = APIRouter(prefix="/dashboard", tags=["Consolidated Dashboard"])


@router.get(
    "/employer/consolidated",
    response_model=EmployerConsolidatedDashboardSchema,
    summary="Get complete employer home screen data",
    description="""
    Returns all data needed for employer home screen in a single response.
    
    Replaces multiple API calls:
    - /employer/dashboard
    - /employer/metrics
    - /employer/activities
    - /employer/jobs/active
    - /employer/applications/pending
    - /workers/nearby/list
    - /workers/top
    - /services/nearby/list
    - Notifications count
    - Messages count
    
    **Benefits:**
    - Single network request instead of 10-15 parallel requests
    - Reduced memory pressure on mobile clients
    - Faster initial page load
    - Better offline support (single cache entry)
    """,
)
async def get_employer_consolidated_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    limit_activities: int = Query(
        10, ge=1, le=50, description="Max number of recent activities"
    ),
    limit_jobs: int = Query(
        5, ge=1, le=20, description="Max number of active jobs"
    ),
    limit_applications: int = Query(
        5, ge=1, le=20, description="Max number of pending applications"
    ),
    limit_workers: int = Query(
        10, ge=1, le=50, description="Max number of nearby/top workers"
    ),
    limit_services: int = Query(
        10, ge=1, le=50, description="Max number of nearby services"
    ),
):
    """
    Get complete employer home screen dashboard.
    
    **Query Parameters:**
    - `limit_activities`: Number of recent activities (default: 10, max: 50)
    - `limit_jobs`: Number of active jobs (default: 5, max: 20)
    - `limit_applications`: Number of pending applications (default: 5, max: 20)
    - `limit_workers`: Number of workers to show (default: 10, max: 50)
    - `limit_services`: Number of services to show (default: 10, max: 50)
    
    **Response includes:**
    - User profile
    - Dashboard metrics (active jobs, applications, earnings, reviews, etc.)
    - Recent activities with rich context
    - Active jobs with analytics
    - Pending applications from workers
    - Nearby and top workers for discovery
    - Nearby services for discovery
    - Unread notification and message counts
    """
    service = ConsolidatedDashboardService(db)
    return await service.get_employer_consolidated_dashboard(
        user_id=current_user.id,
        limit_activities=limit_activities,
        limit_jobs=limit_jobs,
        limit_applications=limit_applications,
        limit_workers=limit_workers,
        limit_services=limit_services,
    )


@router.get(
    "/worker/consolidated",
    response_model=WorkerConsolidatedDashboardSchema,
    summary="Get complete worker home screen data",
    description="""
    Returns all data needed for worker home screen in a single response.
    
    Replaces multiple API calls:
    - /worker/dashboard
    - /worker/dashboard/active-contracts
    - /worker/metrics
    - /jobs/worker/available
    - /worker/dashboard/applications-with-actions
    - Notifications count
    - Messages count
    
    **Benefits:**
    - Single network request instead of 5-10 parallel requests
    - Reduced memory pressure on mobile clients
    - Faster initial page load
    - Better offline support (single cache entry)
    """,
)
async def get_worker_consolidated_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.WORKER)),
    limit_jobs: int = Query(
        5, ge=1, le=20, description="Max number of recommended jobs"
    ),
    limit_applications: int = Query(
        10, ge=1, le=50, description="Max number of applications to show"
    ),
    limit_activities: int = Query(
        10, ge=1, le=50, description="Max number of recent activities"
    ),
):
    """
    Get complete worker home screen dashboard.
    
    **Query Parameters:**
    - `limit_jobs`: Number of recommended jobs (default: 5, max: 20)
    - `limit_applications`: Number of applications (default: 10, max: 50)
    - `limit_activities`: Number of recent activities (default: 10, max: 50)
    
    **Response includes:**
    - User profile
    - Dashboard statistics (applications, contracts, earnings, completed jobs)
    - Recommended available jobs
    - User's job applications
    - Recent activity
    - Applications with recommended actions (boost, follow-up, mark complete, etc.)
    - Recent boost activities
    - Unread notification and message counts
    """
    service = ConsolidatedDashboardService(db)
    return await service.get_worker_consolidated_dashboard(
        user_id=current_user.id,
        limit_jobs=limit_jobs,
        limit_applications=limit_applications,
        limit_activities=limit_activities,
    )
