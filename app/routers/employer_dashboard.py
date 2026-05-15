from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional

from app.models.user import User, UserRole
from app.models.job_application import ApplicationStatus
from app.schemas.employer_dashboard import (
    DashboardMetricsSchema,
    EmployerDashboardSchema,
    EnrichedRecentActivitySchema,
    ActiveJobSchema,
    PaymentSummarySchema,
    PaymentHistorySchema,
    JobApplicationDetailSchema,
    UnreadNotificationCountSchema,
    EmployerWalletSchema
)
from app.schemas.job_application import JobApplicationInDB
from app.services.employer_dashboard_service import EmployerDashboardService
from app.database import get_db
from app.utils.security import get_current_user, check_permissions

router = APIRouter(prefix="/employer", tags=["Employer Dashboard"])


@router.get("/dashboard", response_model=EmployerDashboardSchema)
async def get_employer_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get complete employer dashboard with all metrics, activities, jobs, and payments
    
    Returns:
    - metrics: Dashboard statistics
    - recent_activities: User's recent activities
    - active_jobs_list: Currently active jobs
    - pending_applications: Pending job applications
    - payment_summary: Payment overview
    """
    dashboard_service = EmployerDashboardService(db)
    dashboard = await dashboard_service.get_complete_dashboard(current_user.id)
    return dashboard


@router.get("/metrics", response_model=DashboardMetricsSchema)
async def get_dashboard_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get dashboard metrics only (active jobs, applications, earnings, etc.)
    """
    dashboard_service = EmployerDashboardService(db)
    metrics = await dashboard_service.get_dashboard_metrics(current_user.id)
    return metrics


@router.get("/activities", response_model=List[EnrichedRecentActivitySchema])
async def get_recent_activities(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get enriched recent activities with context about jobs, workers, etc.
    """
    dashboard_service = EmployerDashboardService(db)
    activities = await dashboard_service.get_enriched_recent_activities(current_user.id, limit=limit)
    return activities


@router.get("/jobs/active", response_model=List[ActiveJobSchema])
async def get_active_jobs(
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get active jobs with analytics (applications count, views, completion status)
    """
    dashboard_service = EmployerDashboardService(db)
    jobs = await dashboard_service.get_active_jobs(current_user.id, limit=limit)
    return jobs


@router.get("/payments/summary", response_model=PaymentSummarySchema)
async def get_payment_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get payment summary (earnings, pending, released, wallet balance)
    """
    dashboard_service = EmployerDashboardService(db)
    summary = await dashboard_service.get_payment_summary(current_user.id)
    return summary


@router.get("/payments/history", response_model=List[PaymentHistorySchema])
async def get_payment_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get payment history with details about each transaction
    """
    dashboard_service = EmployerDashboardService(db)
    history = await dashboard_service.get_payment_history(current_user.id, skip=skip, limit=limit)
    return history


@router.get("/applications/pending", response_model=List[JobApplicationDetailSchema])
async def get_pending_applications(
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get pending job applications with worker details and ratings
    """
    dashboard_service = EmployerDashboardService(db)
    applications = await dashboard_service.get_pending_applications(current_user.id, limit=limit)
    return applications


@router.get("/notifications/unread", response_model=UnreadNotificationCountSchema)
async def get_unread_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get count of unread notifications
    """
    dashboard_service = EmployerDashboardService(db)
    count = await dashboard_service.get_unread_notification_count(current_user.id)
    return count


@router.get("/wallet", response_model=EmployerWalletSchema)
async def get_wallet_details(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get wallet details (balance and recent transactions)
    """
    dashboard_service = EmployerDashboardService(db)
    wallet_details = await dashboard_service.get_wallet_details(current_user.id)
    return wallet_details


@router.get("/workers/recent", response_model=List[Dict[str, Any]])
async def get_recent_workers(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get recently paid workers
    """
    dashboard_service = EmployerDashboardService(db)
    workers = await dashboard_service.get_recent_workers(current_user.id, limit=limit)
    return workers


@router.get("/activity", response_model=List[EnrichedRecentActivitySchema])
async def get_recent_activity(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get a detailed list of recent activities
    """
    dashboard_service = EmployerDashboardService(db)
    activities = await dashboard_service.get_recent_activity(current_user.id, limit=limit)
    return activities


@router.get("/applications", response_model=List[JobApplicationInDB])
async def get_all_applications(
    status: Optional[ApplicationStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get all job applications for the current employer, with optional status filtering.
    """
    dashboard_service = EmployerDashboardService(db)
    applications = await dashboard_service.get_all_applications(current_user.id, status=status)
    return applications

@router.get("/applications/stats", response_model=Dict[str, int])
async def get_application_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER))
):
    """
    Get statistics about job applications for the current employer.
    """
    dashboard_service = EmployerDashboardService(db)
    stats = await dashboard_service.get_application_stats(current_user.id)
    return stats
