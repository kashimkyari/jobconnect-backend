"""
Consolidated Dashboard Service

Orchestrates all data needed for employer and worker home screens.
Returns complete dashboard responses without requiring multiple client-side API calls.
"""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.user import User
from app.services.employer_dashboard_service import EmployerDashboardService
from app.services.worker_dashboard_service import (
    get_worker_stats,
    get_applications_with_actions,
    get_boost_activities,
    get_worker_dashboard_data,
)
from app.services.notification_service import NotificationService
from app.services.job_service import JobService
from app.services.recent_activity_service import RecentActivityService
from app.services.message_service import MessageService
from app.schemas.consolidated_dashboard import (
    EmployerConsolidatedDashboardSchema,
    WorkerConsolidatedDashboardSchema,
    DashboardMetadata,
    PendingApplicationSchema,
    DensityPointSchema,
)
from app.schemas.user import UserOut
from app.models.job_application import JobApplication, ApplicationStatus
from app.models.notification import Notification
from app.models.message import Message


class ConsolidatedDashboardService:
    """Service for generating consolidated dashboard responses"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.employer_service = EmployerDashboardService(db)
        self.notification_service = NotificationService(db)
        self.job_service = JobService(db)
        self.activity_service = RecentActivityService(db)
        self.message_service = MessageService(db)
        self._density_points_limit = 150

    async def get_employer_consolidated_dashboard(
        self,
        user_id: int,
        limit_activities: int = 10,
        limit_jobs: int = 5,
        limit_applications: int = 5,
        limit_workers: int = 10,
        limit_services: int = 10,
    ) -> EmployerConsolidatedDashboardSchema:
        """
        Get complete employer dashboard with all data in a single response.
        Uses server-side parallelization to fetch all data efficiently.
        """
        
        # Fetch user
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        user_schema = UserOut.from_orm(user)
        
        # Parallel fetch: Main dashboard components
        # Group 1: Core metrics and data
        metrics_task = self.employer_service.get_dashboard_metrics(user_id)
        activities_task = self.employer_service.get_enriched_recent_activities(
            user_id, limit=limit_activities
        )
        jobs_task = self.employer_service.get_active_jobs(user_id, limit=limit_jobs)
        
        # Group 2: Applications and discovery
        pending_apps_task = self._get_pending_applications(user_id, limit=limit_applications)
        nearby_workers_task = self._get_nearby_workers(user_id, limit=limit_workers)
        top_workers_task = self._get_top_workers(user_id, limit=limit_workers)
        nearby_services_task = self._get_nearby_services(user_id, limit=limit_services)
        
        # Group 3: Notification and message counts
        unread_notif_task = self._get_unread_notifications_count(user_id)
        unread_messages_task = self._get_unread_messages_count(user_id)
        
        # Execute all tasks in parallel
        (
            stats,
            recent_activities,
            active_jobs,
            pending_applications,
            nearby_workers,
            top_workers,
            nearby_services,
            unread_notifications_count,
            unread_messages_count,
        ) = await asyncio.gather(
            metrics_task,
            activities_task,
            jobs_task,
            pending_apps_task,
            nearby_workers_task,
            top_workers_task,
            nearby_services_task,
            unread_notif_task,
            unread_messages_task,
        )
        category_counts, density_points = self._build_employer_category_data(nearby_services)
        
        metadata = DashboardMetadata(created_at=datetime.now(timezone.utc))
        
        return EmployerConsolidatedDashboardSchema(
            metadata=metadata,
            user=user_schema,
            stats=stats,
            recent_activities=recent_activities,
            active_jobs=active_jobs,
            pending_applications=pending_applications,
            nearby_workers=nearby_workers,
            top_workers=top_workers,
            nearby_services=nearby_services,
            category_counts=category_counts,
            density_points=density_points,
            unread_notifications_count=unread_notifications_count,
            unread_messages_count=unread_messages_count,
        )

    async def get_worker_consolidated_dashboard(
        self,
        user_id: int,
        limit_jobs: int = 5,
        limit_applications: int = 10,
        limit_activities: int = 10,
        limit_actions: int = 3,
        limit_boosts: int = 5,
    ) -> WorkerConsolidatedDashboardSchema:
        """
        Get complete worker dashboard with all data in a single response.
        Uses server-side parallelization to fetch all data efficiently.
        """
        
        # Fetch user
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        user_schema = UserOut.from_orm(user)
        
        # Parallel fetch all dashboard components
        stats_task = get_worker_stats(self.db, user_id)
        recommended_jobs_task = self.job_service.get_recommended_jobs(
            user, limit=limit_jobs
        )
        applications_task = self._get_worker_applications(user_id, limit=limit_applications)
        recent_activity_task = self.activity_service.get_recent_activities(
            user_id, limit=limit_activities
        )
        applications_with_actions_task = get_applications_with_actions(self.db, user_id)
        boost_activities_task = get_boost_activities(self.db, user_id)
        unread_notif_task = self._get_unread_notifications_count(user_id)
        unread_messages_task = self._get_unread_messages_count(user_id)
        
        # Execute all tasks in parallel
        (
            stats,
            recommended_jobs,
            applications,
            recent_activity,
            applications_with_actions,
            boost_activities,
            unread_notifications_count,
            unread_messages_count,
        ) = await asyncio.gather(
            stats_task,
            recommended_jobs_task,
            applications_task,
            recent_activity_task,
            applications_with_actions_task,
            boost_activities_task,
            unread_notif_task,
            unread_messages_task,
            return_exceptions=True,  # Don't fail entire response if one task fails
        )
        
        # Handle exceptions in parallel tasks
        if isinstance(recommended_jobs, Exception):
            recommended_jobs = []
        if isinstance(applications, Exception):
            applications = []
        if isinstance(recent_activity, Exception):
            recent_activity = []
        if isinstance(applications_with_actions, Exception):
            applications_with_actions = []
        if isinstance(boost_activities, Exception):
            boost_activities = []
        if isinstance(unread_notifications_count, Exception):
            unread_notifications_count = 0
        if isinstance(unread_messages_count, Exception):
            unread_messages_count = 0
        category_counts, density_points = self._build_worker_category_data(
            recommended_jobs if isinstance(recommended_jobs, list) else []
        )
        
        metadata = DashboardMetadata(created_at=datetime.now(timezone.utc))
        
        return WorkerConsolidatedDashboardSchema(
            metadata=metadata,
            user=user_schema,
            stats=stats,
            recommended_jobs=recommended_jobs,
            applications=applications,
            recent_activity=recent_activity,
            applications_with_actions=applications_with_actions,
            boost_activities=boost_activities,
            category_counts=category_counts,
            density_points=density_points,
            unread_notifications_count=unread_notifications_count,
            unread_messages_count=unread_messages_count,
        )

    # ========================================================================
    # Helper methods for data fetching
    # ========================================================================

    async def _get_pending_applications(
        self, employer_id: int, limit: int = 5
    ) -> List[PendingApplicationSchema]:
        """Get pending applications for employer's jobs"""
        from app.models.job import Job
        
        query = (
            select(JobApplication)
            .join(Job)
            .where(
                and_(
                    Job.employer_id == employer_id,
                    JobApplication.status == ApplicationStatus.PENDING,
                )
            )
            .order_by(JobApplication.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        applications = result.scalars().all()
        
        return [
            PendingApplicationSchema(
                id=app.id,
                job_id=app.job_id,
                worker_id=app.worker_id,
                worker_name=f"{app.worker.first_name} {app.worker.last_name}".strip()
                if app.worker
                else "Unknown",
                worker_avatar=app.worker.avatar_url if app.worker else None,
                worker_rating=app.worker.reputation_score if app.worker else 0.0,
                proposal=app.proposal,
                status=app.status.value,
                applied_at=app.created_at,
            )
            for app in applications
        ]

    async def _get_nearby_workers(
        self, employer_id: int, limit: int = 10
    ) -> List:
        """Get nearby workers (delegates to existing service)"""
        try:
            return await self.employer_service.get_nearby_workers(employer_id, limit=limit)
        except Exception:
            return []

    async def _get_top_workers(
        self, employer_id: int, limit: int = 10
    ) -> List:
        """Get top-rated workers (delegates to existing service)"""
        try:
            return await self.employer_service.get_top_workers(employer_id, limit=limit)
        except Exception:
            return []

    async def _get_nearby_services(
        self, employer_id: int, limit: int = 10
    ) -> List:
        """Get nearby services (delegates to existing service)"""
        try:
            return await self.employer_service.get_nearby_services(employer_id, limit=limit)
        except Exception:
            return []

    async def _get_worker_applications(
        self, worker_id: int, limit: int = 10
    ) -> List:
        """Get worker's job applications"""
        from sqlalchemy.orm import selectinload
        
        query = (
            select(JobApplication)
            .where(JobApplication.worker_id == worker_id)
            .options(selectinload(JobApplication.job))
            .order_by(JobApplication.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def _get_unread_notifications_count(self, user_id: int) -> int:
        """Get count of unread notifications"""
        query = select(func.count(Notification.id)).where(
            and_(Notification.user_id == user_id, Notification.read == False)
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def _get_unread_messages_count(self, user_id: int) -> int:
        """Get count of unread messages"""
        query = select(func.count(Message.id)).where(
            and_(
                Message.receiver_id == user_id,
                Message.is_read == False,
            )
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    def _build_employer_category_data(self, nearby_services: List) -> tuple[dict[str, int], list[DensityPointSchema]]:
        """Build lightweight category counts and map points from nearby services."""
        category_counts: dict[str, int] = {}
        density_points: list[DensityPointSchema] = []

        if not isinstance(nearby_services, list):
            return category_counts, density_points

        for service in nearby_services:
            category_key = str(
                getattr(service, "category_name", None)
                or getattr(service, "name", "other")
            ).strip() or "other"
            category_counts[category_key] = category_counts.get(category_key, 0) + 1

            latitude = getattr(service, "latitude", None)
            longitude = getattr(service, "longitude", None)
            if latitude is None or longitude is None:
                continue
            if len(density_points) >= self._density_points_limit:
                continue
            density_points.append(
                DensityPointSchema(
                    id=str(getattr(service, "id", "")),
                    category_id=category_key,
                    latitude=float(latitude),
                    longitude=float(longitude),
                )
            )

        return category_counts, density_points

    def _build_worker_category_data(self, recommended_jobs: List) -> tuple[dict[str, int], list[DensityPointSchema]]:
        """Build lightweight category counts and map points from recommended jobs."""
        category_counts: dict[str, int] = {}
        density_points: list[DensityPointSchema] = []

        if not isinstance(recommended_jobs, list):
            return category_counts, density_points

        for job in recommended_jobs:
            category_key = str(
                getattr(job, "category_id", None)
                or getattr(job, "category_name", None)
                or "other"
            ).strip() or "other"
            category_counts[category_key] = category_counts.get(category_key, 0) + 1

            latitude = getattr(job, "latitude", None)
            longitude = getattr(job, "longitude", None)
            if latitude is None or longitude is None:
                continue
            if len(density_points) >= self._density_points_limit:
                continue
            density_points.append(
                DensityPointSchema(
                    id=str(getattr(job, "id", "")),
                    category_id=category_key,
                    latitude=float(latitude),
                    longitude=float(longitude),
                )
            )

        return category_counts, density_points
