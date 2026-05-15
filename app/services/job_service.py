from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from typing import List, Optional
import json

from ..models.job import Job, JobStatus, JobLocationType, CompletionStage
from ..models.file import File
from ..models.job_application import JobApplication, ApplicationStatus, ApplicationStatusHistory, ContractStatus
from ..models.payment import PaymentStatus, Payment
from ..models.user import User, UserRole
from ..models.review import Review
from .message_service import MessageService
from .review_service import ReviewService
from .job_state_machine import JobStateMachine, JobRole
from .badge_service import BadgeService
from datetime import datetime, timedelta, timezone
from ..schemas.job import (
    JobCreate,
    JobUpdate,
    JobInDB,
    CompletionStatus,
    ActiveJob,
    EmployerJobDetail,
    WorkerJobDetail,
)
from ..schemas.review import ReviewWithUserDetails
from ..schemas.job_with_applications import JobWithApplications
from ..schemas.job_application import (
    JobApplicationCreate,
    JobApplicationInDB,
)
from ..schemas.applicant import Applicant
from ..schemas.file import FileInDB
from ..utils.cache import (
    get_cache,
    set_cache,
    delete_cache,
    delete_cache_by_prefix,
)
from .kyc_service import KYCService
from .notification_service import NotificationService
from .recent_activity_service import RecentActivityService
from .block_service import BlockService
from ..schemas.notification import NotificationCreate
from ..models.notification import NotificationCategory
from ..schemas.recent_activity import RecentActivityCreate
from .user_service import UserService
from .subscription_service import SubscriptionService
from .transaction_service import TransactionService
from ..websocket_manager import manager as websocket_manager
from ..utils.logging import StructuredLogger
from decimal import Decimal
from ..models.transaction import TransactionType, Transaction, TransactionStatus

JOB_CACHE_VERSION = "v3"
logger = StructuredLogger(__name__)

class JobService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _normalize_text(value: Optional[str]) -> str:
        if hasattr(value, "value"):
            value = value.value
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def _normalize_money(value) -> Optional[str]:
        if value is None:
            return None
        return f"{Decimal(str(value)):.2f}"

    async def _invalidate_job_caches(self, job_id: int, employer_id: int):
        await delete_cache(f"job_{job_id}")
        await delete_cache_by_prefix(f"jobs_{JOB_CACHE_VERSION}")
        await delete_cache_by_prefix(f"employer_jobs_{JOB_CACHE_VERSION}_{employer_id}")

    def _get_completion_status(self, job: Job) -> Optional[CompletionStatus]:
        if job.status == JobStatus.COMPLETED:
            return CompletionStatus.COMPLETED
        if job.worker_completed and not job.employer_completed:
            return CompletionStatus.WAITING_FOR_EMPLOYER
        return None

    def _prepare_job_for_schema(self, job: Job) -> Job:
        """Prepares job object for schema validation."""
        return job

    def _resolve_assigned_worker(self, job: Job) -> Optional[User]:
        """Resolve assigned worker from direct relation or accepted application fallback."""
        if getattr(job, "worker", None):
            return job.worker

        for application in getattr(job, "applications", []) or []:
            if application.status == ApplicationStatus.ACCEPTED and getattr(application, "worker", None):
                return application.worker

        return None

    def _format_category_name(self, category_id: Optional[str]) -> Optional[str]:
        """Convert category_id like 'web-development' to a readable label."""
        if not category_id:
            return None
        normalized = str(category_id).strip()
        if not normalized:
            return None
        return " ".join(
            part.upper() if part.upper() in {"UI", "UX", "QA"} else part.capitalize()
            for part in normalized.replace("_", "-").split("-")
            if part
        )

    def _normalize_skills(self, tags: Optional[list]) -> list[str]:
        """Ensure skills list is clean and de-duplicated."""
        if not tags:
            return []

        cleaned = []
        seen = set()
        for item in tags:
            if item is None:
                continue
            value = str(item).strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(value)
        return cleaned

    def _set_employer_data_safe(self, job_schema, job: Job):
        """Safely set employer data on job schema, handling None employer."""
        if job and job.employer:
            job_schema.employer_first_name = job.employer.first_name
            job_schema.employer_last_name = job.employer.last_name
            job_schema.employer_avatar_url = job.employer.avatar_url
            job_schema.employer_phone = job.employer.phone
            job_schema.employer_email = job.employer.email
        else:
            job_schema.employer_first_name = None
            job_schema.employer_last_name = None
            job_schema.employer_avatar_url = None
            job_schema.employer_phone = None
            job_schema.employer_email = None
        return job_schema

    async def _find_job_by_request_id(self, employer_id: int, request_id: Optional[str]) -> Optional[Job]:
        if not request_id:
            return None

        result = await self.db.execute(
            select(Job)
            .where(
                and_(
                    Job.employer_id == employer_id,
                    Job.last_request_id == request_id,
                )
            )
            .options(
                selectinload(Job.employer),
                selectinload(Job.attachments),
            )
            .order_by(Job.created_at.desc())
        )
        return result.scalars().first()

    async def _resolve_repeat_source_job(self, employer_id: int, repeated_from_job_id: Optional[int]) -> Optional[Job]:
        if not repeated_from_job_id:
            return None

        result = await self.db.execute(
            select(Job).where(
                and_(
                    Job.id == repeated_from_job_id,
                    Job.employer_id == employer_id,
                )
            )
        )
        source_job = result.scalar_one_or_none()
        if not source_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source completed job not found",
            )
        if source_job.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only completed jobs can be reposted",
            )
        return source_job

    async def _find_semantic_duplicate_job(
        self,
        job_data: JobCreate,
        employer_id: int,
        repeated_from_job_id: Optional[int] = None,
    ) -> Optional[Job]:
        if repeated_from_job_id:
            return None

        result = await self.db.execute(
            select(Job)
            .where(
                and_(
                    Job.employer_id == employer_id,
                    Job.is_archived.is_(False),
                    Job.status.in_([JobStatus.DRAFT, JobStatus.OPEN, JobStatus.IN_PROGRESS]),
                )
            )
            .options(
                selectinload(Job.employer),
                selectinload(Job.attachments),
            )
            .order_by(Job.created_at.desc())
            .limit(25)
        )
        existing_jobs = result.scalars().all()

        normalized_title = self._normalize_text(job_data.title)
        normalized_description = self._normalize_text(job_data.description)
        normalized_category = self._normalize_text(job_data.category_id)
        normalized_city = self._normalize_text(job_data.city)
        normalized_country = self._normalize_text(job_data.country)
        payment_type = self._normalize_text(job_data.payment_type)
        location_type = self._normalize_text(job_data.location_type)
        fixed_price = self._normalize_money(job_data.job_price)
        hourly_rate = self._normalize_money(job_data.hourly_rate)
        estimated_hours = int(job_data.estimated_hours or 0)

        for existing in existing_jobs:
            if self._normalize_text(existing.title) != normalized_title:
                continue
            if self._normalize_text(existing.description) != normalized_description:
                continue
            if self._normalize_text(existing.category_id) != normalized_category:
                continue
            if self._normalize_text(existing.city) != normalized_city:
                continue
            if self._normalize_text(existing.country) != normalized_country:
                continue
            if self._normalize_text(existing.payment_type) != payment_type:
                continue
            if self._normalize_text(existing.location_type) != location_type:
                continue
            if self._normalize_money(existing.job_price) != fixed_price:
                continue
            if self._normalize_money(existing.hourly_rate) != hourly_rate:
                continue
            if int(existing.estimated_hours or 0) != estimated_hours:
                continue
            return existing

        return None

    def _build_job_response(self, job: Job) -> JobInDB:
        job = self._prepare_job_for_schema(job)
        job_response = JobInDB.from_orm(job)
        job_response.category_name = None
        job_response = self._set_employer_data_safe(job_response, job)
        job_response.completion_status = self._get_completion_status(job)
        job_response.attachments = [FileInDB.from_orm(attachment) for attachment in job.attachments]
        return job_response

    def _resolve_job_cost(self, job: Job, application: Optional[JobApplication] = None) -> Decimal:
        """Resolve the chargeable amount for a hire across fixed-price and hourly jobs."""
        if job.confirmed_price is not None:
            return Decimal(str(job.confirmed_price))

        if application and application.proposed_budget is not None:
            return Decimal(str(application.proposed_budget))

        if job.job_price is not None:
            return Decimal(str(job.job_price))

        if job.hourly_rate is not None and job.estimated_hours is not None:
            return Decimal(str(job.hourly_rate)) * Decimal(str(job.estimated_hours))

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to determine the hire price for this job"
        )

    async def create_job(self, job_data: JobCreate, employer_id: int, request_id: Optional[str] = None) -> Job:
        existing_request_job = await self._find_job_by_request_id(employer_id, request_id)
        if existing_request_job:
            return self._build_job_response(existing_request_job)

        # Validate that category_id is provided (it's a string identifier like 'healthcare', 'cleaning')
        if not job_data.category_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="category_id is required"
            )

        # Validate payment configuration based on payment_type
        from ..models.job import PaymentType as JobPaymentType
        
        if job_data.payment_type == JobPaymentType.FIXED_PRICE or job_data.payment_type == 'fixed_price':
            if job_data.job_price is None or job_data.job_price <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="job_price is required and must be greater than 0 for fixed price jobs"
                )
        elif job_data.payment_type == JobPaymentType.HOURLY_RATE or job_data.payment_type == 'hourly_rate':
            if job_data.hourly_rate is None or job_data.hourly_rate <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="hourly_rate is required and must be greater than 0 for hourly rate jobs"
                )
            if job_data.estimated_hours is None or job_data.estimated_hours <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="estimated_hours is required and must be greater than 0 for hourly rate jobs"
                )

        repeated_from_job_id = job_data.repeated_from_job_id
        await self._resolve_repeat_source_job(employer_id, repeated_from_job_id)

        duplicate_job = await self._find_semantic_duplicate_job(
            job_data,
            employer_id,
            repeated_from_job_id=repeated_from_job_id,
        )
        if duplicate_job:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A similar active job already exists. Update or repost the existing job instead.",
            )

        job_dict = job_data.dict()
        attachment_ids = job_dict.pop("attachment_ids", [])
        job_dict["last_request_id"] = request_id
        job_dict["last_request_at"] = datetime.now(timezone.utc) if request_id else None

        # Create job in OPEN status - auto-publish on create
        job = Job(**job_dict, employer_id=employer_id, status=JobStatus.OPEN)
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)

        if attachment_ids:
            query = select(File).where(File.id.in_(attachment_ids))
            result = await self.db.execute(query)
            attachments = result.scalars().all()
            for attachment in attachments:
                attachment.reference_id = job.id
                attachment.reference_type = "job"
            job.attachments = attachments

        await self.db.commit()
        await self.db.refresh(job, ["employer", "attachments"])

        # Create notification for admin
        user_service = UserService(self.db)
        admin_ids = await user_service.get_admin_user_ids()
        notification_service = NotificationService(self.db)
        for admin_id in admin_ids:
            await notification_service.create_notification(
                NotificationCreate(
                    user_id=admin_id,
                    title="New Job Posting",
                    message=f"A new job has been posted: {job.title}",
                    category=NotificationCategory.JOBS_AND_MATCHES,
                    action_screen="JobDetails",
                    action_payload={"job_id": job.id}
                )
            )

        await self._invalidate_job_caches(job.id, employer_id)

        # Broadcast job published event (auto-publish)
        try:
            await websocket_manager.broadcast_job_published(
                job_id=job.id,
                job_title=job.title,
                employer_id=employer_id,
                category=job.category_id if job.category_id else "General"
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast job published event: {e}")

        return self._build_job_response(job)

    async def _build_reviews_with_details(self, job: Job) -> List[ReviewWithUserDetails]:
        """Build all reviews for a job with reviewer/reviewee details and role indicators."""
        all_reviews = []
        if not job.reviews:
            return all_reviews
        
        for review in job.reviews:
            review_data = ReviewWithUserDetails(
                id=review.id,
                rating=review.rating,
                comment=review.comment,
                job_id=review.job_id,
                reviewer_id=review.reviewer_id,
                reviewer_name=f"{review.reviewer.first_name} {review.reviewer.last_name}",
                reviewer_avatar=review.reviewer.avatar_url,
                reviewer_role="employer" if review.reviewer_id == job.employer_id else "worker",
                reviewee_id=review.reviewee_id,
                reviewee_name=f"{review.reviewee.first_name} {review.reviewee.last_name}",
                reviewee_avatar=review.reviewee.avatar_url,
                reviewee_role="employer" if review.reviewee_id == job.employer_id else "worker",
                created_at=review.created_at,
                updated_at=review.updated_at,
            )
            all_reviews.append(review_data)
        
        return all_reviews

    async def get_jobs(
        self,
        user_id: Optional[int] = None,
        status: Optional[JobStatus] = None,
        location_type: Optional[JobLocationType] = None,
        category: Optional[str] = None,
        location: Optional[str] = None,
        skip: int = 0,
        limit: int = 10
    ) -> List[JobInDB]:
        query = select(Job).options(
            selectinload(Job.employer),
            selectinload(Job.reviews).selectinload(Review.reviewer),
            selectinload(Job.reviews).selectinload(Review.reviewee),
            selectinload(Job.attachments),
        )
        
        if status:
            query = query.where(Job.status == status)
        else:
            query = query.where(Job.status == JobStatus.OPEN)
            
        if location_type:
            query = query.where(Job.location_type == location_type)
        if category:
            # Category filtering by string ID (client-side managed)
            query = query.where(Job.category_id == category)
        if location:
            query = query.where(Job.location.ilike(f"%{location}%"))
            
        query = query.order_by(Job.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        jobs = result.scalars().all()

        jobs_schema = []
        for job in jobs:
            job = self._prepare_job_for_schema(job)
            job_schema = JobInDB.from_orm(job)
            job_schema.category_name = None
            job_schema = self._set_employer_data_safe(job_schema, job)
            job_schema.completion_status = self._get_completion_status(job)
            job_schema.all_reviews = await self._build_reviews_with_details(job)
            job_schema.attachments = [FileInDB.from_orm(attachment) for attachment in job.attachments]
            jobs_schema.append(job_schema)

        return jobs_schema

    async def get_recommended_jobs(self, user: User, limit: int = 5) -> List[JobInDB]:
        """Get recommended jobs for a worker based on their profile and location.
        
        Uses a combined scoring algorithm:
        - Location score: 0.5 weight - based on distance from worker's location
        - Skills score: 0.5 weight - based on category and skills match
        """
        from .location_service import LocationService
        
        # If worker has no service category, return the latest available jobs
        if not user.service_category:
            return await self.get_available_jobs_for_worker(limit=limit)
        
        # Get all open jobs matching the worker's category (now string-based)
        query = (
            select(Job)
            .where(
                and_(
                    Job.status == JobStatus.OPEN,
                    Job.category_id == user.service_category
                )
            )
            .options(
                selectinload(Job.employer),
                selectinload(Job.attachments),
            )
            .order_by(Job.created_at.desc())
            .limit(limit * 3)  # Get more to score and filter
        )
        
        result = await self.db.execute(query)
        jobs = result.scalars().all()
        
        # Score jobs based on location and skills
        scored_jobs = []
        location_service = LocationService(self.db)
        
        search_radius_km = LocationService.resolve_search_radius_km(user=user)

        for job in jobs:
            # Calculate skills score (category match)
            # Category matching is now done client-side using category_id string comparison
            skills_score = 0.7
            
            # Calculate location score
            location_score = 0.0
            if user.latitude and user.longitude and job.latitude and job.longitude:
                distance = location_service.calculate_distance(
                    user.latitude, user.longitude,
                    job.latitude, job.longitude
                )
                
                # Location score: 1.0 if within radius, decreases with distance
                # Max distance considered: 2x user's preferred search radius
                max_distance = search_radius_km * 2
                if distance <= search_radius_km:
                    location_score = 1.0
                elif distance <= max_distance:
                    location_score = 1.0 - (distance - search_radius_km) / (max_distance - search_radius_km)
                else:
                    location_score = 0.0
            else:
                # If location data not available, give neutral score
                location_score = 0.5
            
            # Combined score: 50% location, 50% skills
            combined_score = (0.5 * location_score) + (0.5 * skills_score)
            scored_jobs.append((job, combined_score))
        
        # Sort by combined score (highest first), then by creation date
        scored_jobs.sort(key=lambda x: (-x[1], -x[0].created_at.timestamp()))
        
        # Convert to schema
        jobs_schema = []
        for job, score in scored_jobs[:limit]:
            job = self._prepare_job_for_schema(job)
            job_schema = JobInDB.from_orm(job)
            job_schema.category_name = None
            job_schema = self._set_employer_data_safe(job_schema, job)
            job_schema.attachments = [FileInDB.from_orm(attachment) for attachment in job.attachments]
            job_schema.is_new = (datetime.now(timezone.utc) - job.created_at) < timedelta(days=1)
            job_schema.city = job.city
            job_schema.country = job.country
            job_schema.location_type = job.location_type
            jobs_schema.append(job_schema)
        
        return jobs_schema

    async def get_available_jobs_for_worker(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[JobInDB]:
        """Get all available (OPEN) jobs for workers."""
        query = (
            select(Job)
            .where(Job.status == JobStatus.OPEN)
            .options(
                selectinload(Job.employer),
                selectinload(Job.attachments),
            )
            .order_by(Job.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        jobs = result.scalars().all()

        review_service = ReviewService(self.db)
        jobs_schema = []
        for job in jobs:
            job = self._prepare_job_for_schema(job)
            job_schema = JobInDB.from_orm(job)
            # category_name is no longer available - category_id is now a client-managed string
            job_schema.category_name = None
            job_schema = self._set_employer_data_safe(job_schema, job)
            job_schema.attachments = [FileInDB.from_orm(attachment) for attachment in job.attachments]
            job_schema.is_new = (datetime.now(timezone.utc) - job.created_at) < timedelta(days=1)
            if job.employer:
                job_schema.employer = job.employer
                job_schema.employer_review_stats = await review_service.get_user_review_stats(job.employer.id)
            jobs_schema.append(job_schema)

        return jobs_schema

    async def get_job(self, job_id: int, user_id: Optional[int] = None, worker_id: Optional[int] = None) -> Optional[JobWithApplications]:
        query = (
            select(Job)
            .where(Job.id == job_id)
            .options(
                selectinload(Job.employer),
                selectinload(Job.worker),
                selectinload(Job.applications).selectinload(JobApplication.worker),
                selectinload(Job.applications).selectinload(JobApplication.status_history),
                selectinload(Job.attachments),
                selectinload(Job.reviews).selectinload(Review.reviewer),
                selectinload(Job.reviews).selectinload(Review.reviewee),
            )
        )
        result = await self.db.execute(query)
        job = result.scalar_one_or_none()

        if job:
            job = self._prepare_job_for_schema(job)
            job_schema = JobWithApplications.from_orm(job)
            job_schema.attachments = [FileInDB.from_orm(attachment) for attachment in job.attachments]
            job_schema.category_name = None
            job_schema = self._set_employer_data_safe(job_schema, job)
            job_schema.completion_status = self._get_completion_status(job)
            job_schema.all_reviews = await self._build_reviews_with_details(job)
            job_schema.location = job.location
            resolved_worker = self._resolve_assigned_worker(job)
            if resolved_worker:
                job_schema.worker = resolved_worker

            if worker_id:
                application = await self.get_worker_application(job_id, worker_id)
                if application:
                    job_schema.application_status = application.status
                    job_schema.boosted = application.boosted
                else:
                    job_schema.application_status = None
                    job_schema.boosted = False

            return job_schema
        return None
    async def get_employer_jobs(self, employer_id: int) -> List[JobWithApplications]:
        """Get all jobs posted by an employer with their applications and details"""
        query = (
            select(Job)
            .where(Job.employer_id == employer_id)
            .options(
                selectinload(Job.employer),
                selectinload(Job.worker),
                selectinload(Job.applications).selectinload(JobApplication.worker),
                selectinload(Job.applications).selectinload(JobApplication.status_history),
                selectinload(Job.reviews).selectinload(Review.reviewer),
                selectinload(Job.reviews).selectinload(Review.reviewee),
                selectinload(Job.attachments),
            )
            .order_by(Job.created_at.desc())
        )
        result = await self.db.execute(query)
        jobs = result.scalars().unique().all()

        jobs_with_applications = []
        for job in jobs:
            try:
                job = self._prepare_job_for_schema(job)
                job_schema = JobWithApplications.from_orm(job)
                job_schema.category_name = None
                
                # Safe access to employer fields with defaults
                # Safe access to employer fields with defaults
                if job.employer:
                    job_schema.employer_first_name = job.employer.first_name or "Unknown"
                    job_schema.employer_last_name = job.employer.last_name or ""
                    job_schema.employer_avatar_url = job.employer.avatar_url or None
                    job_schema.employer_phone = job.employer.phone or None
                    job_schema.employer_email = job.employer.email or None
                else:
                    job_schema.employer_first_name = "Unknown"
                    job_schema.employer_last_name = ""
                    job_schema.employer_avatar_url = None
                    job_schema.employer_phone = None
                    job_schema.employer_email = None

                resolved_worker = self._resolve_assigned_worker(job)
                if resolved_worker:
                    job_schema.worker = resolved_worker

                job_schema.completion_status = self._get_completion_status(job)
                job_schema.all_reviews = await self._build_reviews_with_details(job)
                job_schema.attachments = [FileInDB.from_orm(attachment) for attachment in (job.attachments or [])]
                job_schema.location = job.location
                jobs_with_applications.append(job_schema)
            except Exception as e:
                logger.error(
                    "Error preparing job schema for employer",
                    job_id=job.id if job else None,
                    employer_id=employer_id,
                    error=str(e)
                )
                # Skip problematic jobs instead of crashing
                continue

        return jobs_with_applications

    async def get_employer_active_jobs(self, employer_id: int) -> List[ActiveJob]:
        """Get all active jobs posted by an employer"""
        query = (
            select(Job)
            .where(and_(Job.employer_id == employer_id, Job.status.in_([JobStatus.OPEN, JobStatus.IN_PROGRESS])))
            .options(
                selectinload(Job.employer),
                selectinload(Job.applications).selectinload(JobApplication.worker),
            )
            .order_by(Job.created_at.desc())
        )
        result = await self.db.execute(query)
        jobs = result.scalars().unique().all()

        active_jobs = []
        for job in jobs:
            job_schema = ActiveJob.from_orm(job)
            job_schema.employer = job.employer
            
            # Find the accepted application to get the worker
            for app in job.applications:
                if app.status == ApplicationStatus.ACCEPTED:
                    job_schema.worker = app.worker
                    job_schema.worker_id = app.worker_id
                    break
            
            active_jobs.append(job_schema)

        return active_jobs

    async def get_worker_active_jobs(self, worker_id: int) -> List[ActiveJob]:
        """Get all active jobs for a worker"""
        query = (
            select(Job)
            .join(JobApplication)
            .where(
                and_(
                    JobApplication.worker_id == worker_id,
                    JobApplication.status == ApplicationStatus.ACCEPTED,
                    Job.status == JobStatus.IN_PROGRESS
                )
            )
            .options(
                selectinload(Job.employer),
                selectinload(Job.applications).selectinload(JobApplication.worker)
            )
            .order_by(Job.created_at.desc())
        )
        result = await self.db.execute(query)
        jobs = result.scalars().unique().all()

        active_jobs = []
        for job in jobs:
            job_schema = ActiveJob.from_orm(job)
            job_schema.employer = job.employer
            
            # Find the accepted application to get the worker
            for app in job.applications:
                if app.worker_id == worker_id and app.status == ApplicationStatus.ACCEPTED:
                    job_schema.worker = app.worker
                    job_schema.worker_id = app.worker_id
                    break
            
            active_jobs.append(job_schema)

        return active_jobs

    async def update_job(
        self,
        job_id: int,
        job_update: JobUpdate,
        employer_id: int
    ) -> Optional[JobInDB]:
        query = select(Job).where(Job.id == job_id).options(
            selectinload(Job.attachments)
        )
        result = await self.db.execute(query)
        job = result.scalar_one_or_none()
        
        if not job:
            return None
            
        if job.employer_id != employer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this job"
            )
            
        # Update job fields
        job_update_dict = job_update.model_dump(exclude_unset=True)
        attachment_ids = job_update_dict.pop("attachment_ids", [])

        for field, value in job_update_dict.items():
            setattr(job, field, value)

        if attachment_ids:
            # First, dissociate existing attachments if you want to replace them
            job.attachments.clear()
            await self.db.flush()

            # Then, associate new attachments
            query = select(File).where(File.id.in_(attachment_ids))
            result = await self.db.execute(query)
            attachments = result.scalars().all()
            for attachment in attachments:
                attachment.reference_id = job.id
                attachment.reference_type = "job"
                self.db.add(attachment)
            job.attachments.extend(attachments)
            
        await self.db.commit()
        await self.db.refresh(job)

        await self._invalidate_job_caches(job.id, employer_id)
        
        job = self._prepare_job_for_schema(job)
        job_schema = JobInDB.from_orm(job)
        job_schema.category_name = None
        job_schema = self._set_employer_data_safe(job_schema, job)
        job_schema.completion_status = self._get_completion_status(job)
        job_schema.attachments = [FileInDB.from_orm(attachment) for attachment in job.attachments]
        
        return job_schema

    async def create_application(
        self,
        job_id: int,
        application_data: JobApplicationCreate,
        worker_id: int
    ) -> JobApplicationInDB:

        # Fetch the job directly from the database to ensure it's a SQLAlchemy model
        job = await self.db.get(Job, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )



        if job.status != JobStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job is not open for applications"
            )

        # Check if worker has already applied
        existing_application = await self.get_worker_application(job_id, worker_id)
        if existing_application:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You have already submitted an application for this job"
            )

        # Create application
        application_dict = application_data.model_dump()
        if not application_dict.get("payment_required"):
            application_dict["payment_id"] = None
        
        # Auto-populate proposed_budget with job_price if not provided
        if not application_dict.get("proposed_budget"):
            application_dict["proposed_budget"] = job.job_price

        application = JobApplication(
            **application_dict,
            job_id=job_id,
            worker_id=worker_id,
            status=ApplicationStatus.PENDING
        )

        # Add the application and refresh to load relationships
        self.db.add(application)
        await self.db.flush()

        # Create initial status history
        history_entry = ApplicationStatusHistory(
            application_id=application.id,
            status=ApplicationStatus.PENDING
        )
        self.db.add(history_entry)
        await self.db.commit()
        
        # Re-fetch the application with all necessary relationships loaded for the response model
        query = (
            select(JobApplication)
            .where(JobApplication.id == application.id)
            .options(
                selectinload(JobApplication.worker),
                selectinload(JobApplication.job).selectinload(Job.employer),
                selectinload(JobApplication.job).selectinload(Job.attachments),
            )
        )
        result = await self.db.execute(query)
        application = result.scalar_one()
        
        # Create notifications
        notification_service = NotificationService(self.db)
        
        # Notify employer
        await notification_service.create_notification(
            NotificationCreate(
                user_id=job.employer_id,
                title="New Job Application",
                message=f"A new application has been submitted for your job: {job.title}",
                category=NotificationCategory.JOBS_AND_MATCHES,
                action_screen="ApplicantsList",
                action_payload={"job_id": job.id}
            )
        )
        
        # Notify admins
        user_service = UserService(self.db)
        admin_ids = await user_service.get_admin_user_ids()
        for admin_id in admin_ids:
            await notification_service.create_notification(
                NotificationCreate(
                    user_id=admin_id,
                    title="New Job Application",
                    message=f"A new application has been submitted for job: {job.title} by worker: {worker_id}",
                    category=NotificationCategory.JOBS_AND_MATCHES,
                    action_screen="JobApplicants",
                    action_payload={"job_id": job.id}
                )
            )
        
        activity_service = RecentActivityService(self.db)
        await activity_service.create_activity(
            RecentActivityCreate(
                user_id=worker_id,
                activity_type="job_application",
                description=f"Applied for job: {job.title}",
                activity_data={"job_id": job.id, "application_id": application.id},
            )
        )
        
        # Manually construct the response to satisfy JobInDB schema for the job attribute
        job_data = application.job.__dict__
        job_data["category_name"] = None
        
        # Safely set employer data
        if application.job.employer:
            job_data["employer_first_name"] = application.job.employer.first_name
            job_data["employer_last_name"] = application.job.employer.last_name
            job_data["employer_avatar_url"] = application.job.employer.avatar_url
            job_data["employer_phone"] = application.job.employer.phone
            job_data["employer_email"] = application.job.employer.email
        else:
            job_data["employer_first_name"] = None
            job_data["employer_last_name"] = None
            job_data["employer_avatar_url"] = None
            job_data["employer_phone"] = None
            job_data["employer_email"] = None
        
        job_data["attachments"] = [FileInDB.from_orm(attachment) for attachment in application.job.attachments]

        app_data = application.__dict__
        app_data["job"] = job_data
        app_data["worker"] = application.worker

        await self._invalidate_job_caches(job_id, job.employer_id)
        
        # Decrement application limit
        subscription_service = SubscriptionService(self.db)
        await subscription_service.decrement_limit(worker_id, "apply_job")

        return JobApplicationInDB.model_validate(app_data)

    async def withdraw_application(self, job_id: int, worker_id: int) -> JobApplicationInDB:
        application = await self.get_worker_application(job_id, worker_id)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )

        application.status = ApplicationStatus.WITHDRAWN
        application_id = application.id
        await self.db.commit()
        
        return await self.get_application(application_id)

    async def boost_application(self, job_id: int, worker_id: int) -> JobApplicationInDB:
        application = await self.get_worker_application(job_id, worker_id)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )

        if application.boosted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Application has already been boosted."
            )

        job = await self.db.get(Job, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )

        worker = await self.db.get(User, worker_id)
        if not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker not found"
            )

        # Calculate budget based on payment type
        if job.payment_type == 'fixed_price' and job.job_price:
            budget = float(job.job_price)
        elif job.payment_type == 'hourly_rate' and job.hourly_rate and job.estimated_hours:
            budget = float(job.hourly_rate) * float(job.estimated_hours)
        else:
            budget = 0.0
        boost_cost = Decimal(budget) * Decimal('0.05')
        if worker.wallet_balance < boost_cost:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient funds to boost this application."
            )

        transaction_service = TransactionService(self.db)
        await transaction_service.create_transaction(
            user_id=worker_id,
            amount=-boost_cost,
            transaction_type=TransactionType.BOOST.value,
            reference=f"boost_app_{application.id}",
            description=f"Boost for application on job: {job.title}"
        )

        application.boosted = True
        application_id = application.id
        await self.db.commit()
        
        return await self.get_application(application_id)

    async def cancel_job(self, job_id: int, user: User) -> JobInDB:
        job = await self.db.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if user.id not in [job.employer_id, job.worker_id]:
            raise HTTPException(status_code=403, detail="User not authorized to cancel this job")

        # Set dispute_status to CANCELLED instead of changing the job status
        job.dispute_status = 'CANCELLED'
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_worker_application(
        self,
        job_id: int,
        worker_id: int
    ) -> Optional[JobApplication]:
        query = select(JobApplication).where(
            and_(
                JobApplication.job_id == job_id,
                JobApplication.worker_id == worker_id
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_application_by_job_and_worker(self, job_id: int, worker_id: int) -> Optional[JobApplication]:
        """Get a specific application by job ID and worker ID."""
        query = (
            select(JobApplication)
            .where(
                and_(
                    JobApplication.job_id == job_id,
                    JobApplication.worker_id == worker_id
                )
            )
            .options(
                selectinload(JobApplication.worker),
                selectinload(JobApplication.job).selectinload(Job.employer)
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_accepted_application(self, job_id: int) -> Optional[JobApplication]:
        query = select(JobApplication).where(
            and_(
                JobApplication.job_id == job_id,
                JobApplication.status == ApplicationStatus.ACCEPTED
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    async def update_application_status(
        self,
        job_id: int,
        application_id: int,
        new_status: ApplicationStatus,
        employer_id: int = None,
        worker_id: int = None
    ) -> Optional[JobApplicationInDB]:
        # Get application
        query = (
            select(JobApplication)
            .where(JobApplication.id == application_id)
            .options(
                selectinload(JobApplication.job).selectinload(Job.employer),
            )
        )
        result = await self.db.execute(query)
        application = result.scalar_one_or_none()
        
        if not application or application.job_id != job_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )

        if employer_id:
            # Get job and check ownership
            job = application.job
            if not job or job.employer_id != employer_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to update this job application"
                )
            if new_status == ApplicationStatus.ACCEPTED:
                # Idempotency: If already accepted, do nothing further.
                if application.status == ApplicationStatus.ACCEPTED:
                    pass
                # If job is not open, it means another worker was hired.
                elif job.status != JobStatus.OPEN:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Another worker has already been hired for this job."
                    )
                # Otherwise, proceed with hiring checks.
                else:
                    pass

            logger.info(
                "Updating application status by employer",
                application_id=application_id,
                job_id=job_id,
                new_status=new_status.value,
                employer_id=employer_id
            )
            # If accepting application, update job status
            if new_status == ApplicationStatus.ACCEPTED:
                worker = await self.db.get(User, application.worker_id)
                worker.unsuccessful_applications_streak = 0
                
                # Determine the job cost (what the employer will be charged)
                job_cost = self._resolve_job_cost(job, application)
                
                # CRITICAL: Check employer has sufficient funds BEFORE hiring
                employer = job.employer
                employer_query = select(User).where(User.id == employer.id).with_for_update()
                employer_result = await self.db.execute(employer_query)
                employer = employer_result.scalar_one()
                
                if employer.wallet_balance < job_cost:
                    raise HTTPException(
                        status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        detail=f"Insufficient funds to hire this worker. You need ₦{job_cost} but only have ₦{employer.wallet_balance}. Please add funds to your wallet and try again."
                    )
                
                # Check if escrow already exists for this job (idempotency)
                idempotency_key = f"hire_{job_id}_{employer.id}"
                existing_escrow = await self.db.execute(
                    select(Transaction).where(
                        and_(
                            Transaction.idempotency_key == idempotency_key,
                            Transaction.transaction_type == TransactionType.ESCROW_HOLD.value
                        )
                    )
                )
                existing_transaction = existing_escrow.scalar_one_or_none()
                
                # Only deduct funds and create transaction if it doesn't already exist
                if not existing_transaction:
                    # Reserve funds in escrow
                    employer.wallet_balance -= job_cost
                    
                    # Create escrow transaction (funds held) - with idempotency support
                    escrow_transaction = Transaction(
                        user_id=employer.id,
                        job_id=job_id,
                        amount=-job_cost,
                        status=TransactionStatus.PENDING,
                        reference=f"job_escrow_{job_id}_hire",
                        idempotency_key=idempotency_key,
                        description=f"Job escrow hold for: {job.title}",
                        transaction_type=TransactionType.ESCROW_HOLD.value,
                    )
                    self.db.add(escrow_transaction)
                
                logger.info(
                    "Accepting application and updating job status",
                    job_id=job_id,
                    new_status=JobStatus.IN_PROGRESS.value
                )
                job.status = JobStatus.IN_PROGRESS
                job.worker_id = application.worker_id
                job.hired_at = datetime.utcnow()
                
                # Quietly dismiss other pending applications
                from sqlalchemy import update
                await self.db.execute(
                    update(JobApplication)
                    .where(
                        and_(
                            JobApplication.job_id == job_id,
                            JobApplication.id != application.id,
                            JobApplication.status.in_([ApplicationStatus.PENDING, ApplicationStatus.REVIEWING])
                        )
                    )
                    .values(status=ApplicationStatus.REJECTED)
                )
                
                # Use confirmed_price if set, otherwise use proposed_budget
                if not job.confirmed_price:
                    job.confirmed_price = job_cost
                
                application.contract_status = ContractStatus.ACCEPTED

                notification_service = NotificationService(self.db)
                await notification_service.create_notification(
                    NotificationCreate(
                        user_id=application.worker_id,
                        title="You've been hired!",
                        message=f"Congratulations! You've been hired for the job: '{job.title}'.",
                        category=NotificationCategory.JOBS_AND_MATCHES,
                        action_screen="JobDetails",
                        action_payload={"job_id": job_id},
                    )
                )
            
            if new_status == ApplicationStatus.REJECTED:
                worker = await self.db.get(User, application.worker_id)
                if not worker.subscription_status:
                    worker.unsuccessful_applications_streak += 1
                    if worker.unsuccessful_applications_streak >= 3:
                        worker.unsuccessful_applications_streak = 0
                        refund_amount = Decimal('300.00')
                        transaction_service = TransactionService(self.db)
                        await transaction_service.create_transaction(
                            user_id=worker.id,
                            amount=refund_amount,
                            transaction_type=TransactionType.REFUND.value,
                            reference=f"refund_3_apps_{worker.id}",
                            description="Refund for 3 unsuccessful job applications."
                        )
                        notification_service = NotificationService(self.db)
                        await notification_service.create_notification(
                            NotificationCreate(
                                user_id=worker.id,
                                title="Application Fee Refunded",
                                message=f"We've refunded you {refund_amount} Naira for 3 unsuccessful applications. Keep trying!",
                                category=NotificationCategory.PAYMENTS_AND_WALLET
                            )
                        )
        
        if worker_id:
            if application.worker_id != worker_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to update this job application"
                )

            logger.info(
                "Updating application status by worker",
                application_id=application_id,
                job_id=job_id,
                new_status=new_status.value,
                worker_id=worker_id
            )

        # Update status
        application.status = new_status

        # Create status history entry
        history_entry = ApplicationStatusHistory(
            application_id=application.id,
            status=new_status
        )
        self.db.add(history_entry)

        try:
            await self.db.commit()

            # Create a notification for the status update
            notification_service = NotificationService(self.db)
            if employer_id:
                if new_status == ApplicationStatus.REJECTED:
                    message = f"Your application for the job '{application.job.title}' has been rejected."
                    await notification_service.create_notification(
                        NotificationCreate(
                            user_id=application.worker_id,
                            title="Application Status Update",
                            message=message,
                            category=NotificationCategory.JOBS_AND_MATCHES,
                            action_screen="JobDetails",
                            action_payload={"job_id": job_id}
                        )
                    )
            elif worker_id:
                # This would be for withdrawal, etc.
                message = f"An application for your job '{application.job.title}' has been updated to {new_status.value}."
                await notification_service.create_notification(
                    NotificationCreate(
                        user_id=application.job.employer_id,
                        title="Application Status Update",
                        message=message,
                        category=NotificationCategory.JOBS_AND_MATCHES,
                        action_screen="ApplicantsList",
                        action_payload={"job_id": job_id}
                    )
                )
            
            # Re-fetch the application with all necessary relationships loaded for the response model
            query = (
                select(JobApplication)
                .where(JobApplication.id == application.id)
                .options(
                    selectinload(JobApplication.worker),
                    selectinload(JobApplication.job).selectinload(Job.employer),
                    selectinload(JobApplication.status_history)
                )
            )
            result = await self.db.execute(query)
            application = result.scalar_one()
            
            logger.info(
                "Successfully updated application status",
                application_id=application_id,
                new_status=application.status.value
            )
            
            # Manually construct the response to include employer and worker details
            job_data = application.job
            
            app_data = application.__dict__
            app_data["job"] = job_data
            app_data["worker"] = application.worker

            await self._invalidate_job_caches(job_id, job_data.employer_id)
            
            return JobApplicationInDB.from_orm(application)
        except Exception as e:
            logger.error(
                "Failed to update application status",
                application_id=application_id,
                error=str(e)
            )
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update application status"
            )

    async def confirm_hire_with_negotiation(
        self,
        job_id: int,
        application_id: int,
        negotiated_price: Optional[float],
        contract_details: Optional[str],
        action: str,
        employer_id: int
    ) -> dict:
        """
        Handle hiring confirmation with optional price negotiation.
        If action is 'accept', hire the worker immediately at their proposed price.
        If action is 'negotiate', send counter-offer to worker.
        """
        # Fetch the application
        query = (
            select(JobApplication)
            .where(JobApplication.id == application_id)
            .options(
                selectinload(JobApplication.job).selectinload(Job.employer),
                selectinload(JobApplication.worker),
            )
        )
        result = await self.db.execute(query)
        application = result.scalar_one_or_none()
        
        if not application or application.job_id != job_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        job = application.job
        if job.employer_id != employer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to hire for this job"
            )
        
        if job.status != JobStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another worker has already been hired for this job"
            )
        
        if application.status not in [ApplicationStatus.PENDING, ApplicationStatus.REVIEWING]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Application cannot be accepted in its current state"
            )
        
        if action == "accept":
            # Accept the worker's proposed price
            # IMPORTANT: Check for sufficient funds BEFORE hiring
            job_cost = self._resolve_job_cost(job, application)
            employer = job.employer
            
            # Lock employer for fund check
            employer_query = select(User).where(User.id == employer.id).with_for_update()
            employer_result = await self.db.execute(employer_query)
            employer = employer_result.scalar_one()
            
            if employer.wallet_balance < job_cost:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=f"Insufficient funds to hire this worker. You need ₦{job_cost} but only have ₦{employer.wallet_balance}. Please add funds to your wallet and try again."
                )
            
            # Check if escrow already exists for this job (idempotency)
            idempotency_key = f"hire_{job_id}_{employer.id}"
            existing_escrow = await self.db.execute(
                select(Transaction).where(
                    and_(
                        Transaction.idempotency_key == idempotency_key,
                        Transaction.transaction_type == TransactionType.ESCROW_HOLD.value
                    )
                )
            )
            existing_transaction = existing_escrow.scalar_one_or_none()
            
            # Only deduct funds and create transaction if it doesn't already exist
            if not existing_transaction:
                # Reserve funds in escrow
                employer.wallet_balance -= job_cost
                
                # Create escrow transaction (funds held) - with idempotency support
                escrow_transaction = Transaction(
                    user_id=employer.id,
                    job_id=job_id,
                    amount=-job_cost,
                    status=TransactionStatus.PENDING,
                    reference=f"job_escrow_{job_id}_hire",
                    idempotency_key=idempotency_key,
                    description=f"Job escrow hold for: {job.title}",
                    transaction_type=TransactionType.ESCROW_HOLD.value,
                )
                self.db.add(escrow_transaction)
            
            job.status = JobStatus.IN_PROGRESS
            job.worker_id = application.worker_id
            job.hired_at = datetime.utcnow()
            job.confirmed_price = job_cost
            job.contract_details = contract_details or job.contract_details
            
            application.status = ApplicationStatus.ACCEPTED
            application.contract_status = ContractStatus.ACCEPTED
            
            # Quietly dismiss other pending applications
            from sqlalchemy import update
            await self.db.execute(
                update(JobApplication)
                .where(
                    and_(
                        JobApplication.job_id == job_id,
                        JobApplication.id != application.id,
                        JobApplication.status.in_([ApplicationStatus.PENDING, ApplicationStatus.REVIEWING])
                    )
                )
                .values(status=ApplicationStatus.REJECTED)
            )
            
            worker = await self.db.get(User, application.worker_id)
            worker.unsuccessful_applications_streak = 0
            
            # Create status history
            history_entry = ApplicationStatusHistory(
                application_id=application.id,
                status=ApplicationStatus.ACCEPTED
            )
            self.db.add(history_entry)
            
            await self.db.commit()
            
            # Notify worker
            notification_service = NotificationService(self.db)
            await notification_service.create_notification(
                NotificationCreate(
                    user_id=application.worker_id,
                    title="You've been hired!",
                    message=f"Congratulations! Your application for '{job.title}' has been accepted.",
                    category=NotificationCategory.JOBS_AND_MATCHES,
                    action_screen="JobDetails",
                    action_payload={"job_id": job_id},
                )
            )
            
            await self._invalidate_job_caches(job_id, employer_id)
            
            return {
                "application_id": application.id,
                "job_id": job_id,
                "worker_id": application.worker_id,
                "original_price": float(job.job_price),
                "negotiated_price": None,
                "status": "accepted",
                "contract_details": job.contract_details,
                "created_at": job.hired_at
            }
        
        elif action == "negotiate":
            # Counter-offer with different price
            if negotiated_price is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Negotiated price is required when action is 'negotiate'"
                )
            
            job.confirmed_price = Decimal(str(negotiated_price))
            job.contract_details = contract_details or job.contract_details
            
            application.status = ApplicationStatus.OFFER_DECLINED  # Temp status: waiting for worker response
            
            # Create status history
            history_entry = ApplicationStatusHistory(
                application_id=application.id,
                status=ApplicationStatus.OFFER_DECLINED
            )
            self.db.add(history_entry)
            
            await self.db.commit()
            
            # Notify worker of counter-offer
            notification_service = NotificationService(self.db)
            await notification_service.create_notification(
                NotificationCreate(
                    user_id=application.worker_id,
                    title="New offer for your application",
                    message=f"The employer has sent a counter-offer for '{job.title}' at {negotiated_price} Naira. Review and respond.",
                    category=NotificationCategory.JOBS_AND_MATCHES,
                    action_screen="JobDetails",
                    action_payload={"job_id": job_id, "application_id": application.id},
                )
            )
            
            await self._invalidate_job_caches(job_id, employer_id)
            
            return {
                "application_id": application.id,
                "job_id": job_id,
                "worker_id": application.worker_id,
                "original_price": float(job.job_price),
                "negotiated_price": float(negotiated_price),
                "status": "pending_worker_response",
                "contract_details": job.contract_details,
                "created_at": datetime.utcnow()
            }
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Action must be 'accept' or 'negotiate'"
            )

    async def get_application(self, application_id: int) -> Optional[JobApplicationInDB]:
        """Get a job application by ID"""
        query = (
            select(JobApplication)
            .where(JobApplication.id == application_id)
            .options(
                selectinload(JobApplication.worker),
                selectinload(JobApplication.job).selectinload(Job.employer),
                selectinload(JobApplication.job).selectinload(Job.attachments),
                selectinload(JobApplication.status_history),
            )
        )
        result = await self.db.execute(query)
        application = result.scalar_one_or_none()

        if not application:
            return None

        # Manually construct the response to include employer and worker details
        job_data = application.job.__dict__
        job_data["category_name"] = None
        
        # Safely set employer data
        if application.job.employer:
            job_data["employer_first_name"] = application.job.employer.first_name
            job_data["employer_last_name"] = application.job.employer.last_name
            job_data["employer_avatar_url"] = application.job.employer.avatar_url
            job_data["employer_phone"] = application.job.employer.phone
            job_data["employer_email"] = application.job.employer.email
        else:
            job_data["employer_first_name"] = None
            job_data["employer_last_name"] = None
            job_data["employer_avatar_url"] = None
            job_data["employer_phone"] = None
            job_data["employer_email"] = None
        
        job_data["attachments"] = [FileInDB.from_orm(attachment) for attachment in application.job.attachments]
        
        app_data = application.__dict__
        app_data["job"] = job_data
        app_data["worker"] = application.worker
        
        return JobApplicationInDB.model_validate(app_data)

    async def get_employer_applications(
        self,
        employer_id: int,
        status: Optional[ApplicationStatus] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[JobApplicationInDB]:
        """Get all applications for jobs posted by an employer."""
        query = (
            select(JobApplication)
            .join(Job)
            .where(Job.employer_id == employer_id)
            .options(
                selectinload(JobApplication.worker),
                selectinload(JobApplication.job).selectinload(Job.employer),
                selectinload(JobApplication.job).selectinload(Job.attachments),
                selectinload(JobApplication.status_history),
            )
            .order_by(JobApplication.created_at.desc())
        )

        if status:
            query = query.where(JobApplication.status == status)

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        applications = result.scalars().unique().all()

        application_schemas = []
        for app in applications:
            job_data = app.job.__dict__.copy()
            job_data["category_name"] = None
            
            if app.job.employer:
                job_data["employer_first_name"] = app.job.employer.first_name
                job_data["employer_last_name"] = app.job.employer.last_name
                job_data["employer_avatar_url"] = app.job.employer.avatar_url
                job_data["employer_phone"] = app.job.employer.phone
                job_data["employer_email"] = app.job.employer.email
            else:
                job_data["employer_first_name"] = None
                job_data["employer_last_name"] = None
                job_data["employer_avatar_url"] = None
                job_data["employer_phone"] = None
                job_data["employer_email"] = None
            
            job_data["attachments"] = [FileInDB.from_orm(attachment) for attachment in app.job.attachments]
            
            app_data = app.__dict__.copy()
            app_data["job"] = job_data
            app_data["worker"] = app.worker
            
            application_schemas.append(JobApplicationInDB.model_validate(app_data))
            
        return application_schemas

    async def get_worker_applications(self, worker_id: int) -> List[JobApplicationInDB]:
        query = (
            select(JobApplication)
            .where(JobApplication.worker_id == worker_id)
            .options(
                selectinload(JobApplication.job).selectinload(Job.employer),
                selectinload(JobApplication.job).selectinload(Job.reviews).selectinload(Review.reviewer),
                selectinload(JobApplication.job).selectinload(Job.reviews).selectinload(Review.reviewee),
                selectinload(JobApplication.job).selectinload(Job.attachments),
                selectinload(JobApplication.status_history),
                selectinload(JobApplication.worker),
            )
            .order_by(JobApplication.created_at.desc())
        )
        result = await self.db.execute(query)
        applications = result.scalars().unique().all()

        application_schemas = []
        for app in applications:
            all_reviews = await self._build_reviews_with_details(app.job)

            job_data = app.job.__dict__.copy()
            job_data["category_name"] = None
            
            # Safely set employer data
            if app.job.employer:
                job_data["employer_first_name"] = app.job.employer.first_name
                job_data["employer_last_name"] = app.job.employer.last_name
                job_data["employer_avatar_url"] = app.job.employer.avatar_url
                job_data["employer_phone"] = app.job.employer.phone
                job_data["employer_email"] = app.job.employer.email
            else:
                job_data["employer_first_name"] = None
                job_data["employer_last_name"] = None
                job_data["employer_avatar_url"] = None
                job_data["employer_phone"] = None
                job_data["employer_email"] = None
            
            job_data["all_reviews"] = all_reviews
            job_data["attachments"] = [FileInDB.from_orm(attachment) for attachment in app.job.attachments]
            
            app_data = app.__dict__.copy()
            app_data["job"] = job_data
            app_data["worker"] = app.worker
            
            application_schemas.append(JobApplicationInDB.model_validate(app_data))

            
        return application_schemas
    async def mark_job_as_complete(self, job_id: int, user: User, request_id: Optional[str] = None) -> JobInDB:
        """
        Mark a job as complete - REQUIRES BOTH PARTIES TO CONFIRM.
        
        Uses transactions table as SINGLE SOURCE OF TRUTH for payment state.
        - ESCROW_HOLD: Created at hire time (funds reserved)
        - ESCROW_RELEASE: Created when BOTH parties confirm completion (funds released to worker)
        
        Behavior:
        1. First party marks complete: Sets their completion flag (worker_completed or employer_completed)
        2. Second party marks complete: BOTH flags are now true, FUNDS RELEASED INSTANTLY to worker
        3. Retry: If already released, returns success (idempotent)
        
        This ensures funds never get stuck and no one loses money on failed requests.
        """
        # Lock job to prevent race conditions
        query = select(Job).where(Job.id == job_id).options(
            selectinload(Job.employer),
            selectinload(Job.attachments),
            selectinload(Job.worker)
        ).with_for_update()
        result = await self.db.execute(query)
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )

        # Check for disputes
        if job.dispute_status and job.dispute_status == 'DISPUTED':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot complete a job with an open dispute.",
            )

        # Validate user authorization
        if user.role == UserRole.WORKER:
            application = await self.get_worker_application(job_id, user.id)
            if not application or application.status != ApplicationStatus.ACCEPTED:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to mark this job as complete"
                )
        elif user.role == UserRole.EMPLOYER:
            if job.employer_id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to complete this job"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action"
            )

        # Get the escrowed amount from the HOLD transaction
        escrow_query = select(Transaction).where(
            Transaction.reference == f"job_escrow_{job_id}_hire",
            Transaction.status == TransactionStatus.PENDING
        )
        escrow_result = await self.db.execute(escrow_query)
        escrow_hold = escrow_result.scalar_one_or_none()
        
        if not escrow_hold:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No escrowed funds found. Job may not have been properly hired."
            )
        
        job_cost = abs(escrow_hold.amount)  # Amount is negative on hold, make it positive
        
        async def _load_job_for_response(target_job_id: int) -> Job:
            """Reload job with required relations to avoid async lazy-load during schema serialization."""
            response_query = select(Job).where(Job.id == target_job_id).options(
                selectinload(Job.employer),
                selectinload(Job.attachments),
                selectinload(Job.worker)
            )
            response_result = await self.db.execute(response_query)
            return response_result.scalar_one()

        # Check if payment already released (idempotency check)
        release_query = select(Transaction).where(
            Transaction.reference.like(f"job_payment_{job_id}_worker_%"),
            Transaction.status == TransactionStatus.SUCCESS,
            Transaction.transaction_type == TransactionType.ESCROW_RELEASE.value
        )
        release_result = await self.db.execute(release_query)
        existing_release = release_result.scalar_one_or_none()
        
        if existing_release:
            # Payment already released - this is a retry or second party confirming
            # Just mark job as complete and return success (idempotent)
            if job.status != JobStatus.COMPLETED:
                job.completion_stage = CompletionStage.PAID
                job.status = JobStatus.COMPLETED
                job.completed_at = func.now()
                job.worker_completed = True
                job.employer_completed = True
                await self.db.commit()
            
            # Return success response
            job = await _load_job_for_response(job_id)
            job = self._prepare_job_for_schema(job)
            job_schema = JobInDB.from_orm(job)
            job_schema.category_name = None
            job_schema = self._set_employer_data_safe(job_schema, job)
            job_schema.completion_status = self._get_completion_status(job)
            job_schema.attachments = [FileInDB.from_orm(attachment) for attachment in job.attachments]
            return job_schema

        # Update completion flags
        if user.role == UserRole.WORKER:
            job.worker_completed = True
        elif user.role == UserRole.EMPLOYER:
            job.employer_completed = True

        # Check if BOTH parties have now confirmed completion
        both_confirmed = job.worker_completed and job.employer_completed
        
        if not both_confirmed:
            # Only first party confirmed - just mark their flag and return
            logger.info(
                "Job completion marked by one party",
                job_id=job_id,
                user_role=user.role,
                worker_completed=job.worker_completed,
                employer_completed=job.employer_completed
            )
            await self.db.commit()
            
            # Return job state showing pending confirmation
            job = await _load_job_for_response(job_id)
            job = self._prepare_job_for_schema(job)
            job_schema = JobInDB.from_orm(job)
            job_schema.category_name = None
            job_schema = self._set_employer_data_safe(job_schema, job)
            job_schema.completion_status = self._get_completion_status(job)
            job_schema.attachments = [FileInDB.from_orm(attachment) for attachment in job.attachments]
            return job_schema

        # BOTH CONFIRMED: RELEASE FUNDS INSTANTLY
        # Lock both users and release escrow atomically
        employer = job.employer
        worker = job.worker
        
        # Lock both for atomic payment processing
        employer_query = select(User).where(User.id == employer.id).with_for_update()
        employer_result = await self.db.execute(employer_query)
        employer = employer_result.scalar_one_or_none()
        
        worker_query = select(User).where(User.id == worker.id).with_for_update()
        worker_result = await self.db.execute(worker_query)
        worker = worker_result.scalar_one_or_none()
        
        if not employer or not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employer or worker not found"
            )

        idempotency_key = request_id or f"complete_{job_id}_{int(datetime.utcnow().timestamp())}"
        
        # Create ESCROW_RELEASE transaction (worker credit)
        # This is the SINGLE source of truth for payment completion
        worker_transaction = Transaction(
            user_id=worker.id,
            job_id=job_id,
            amount=job_cost,
            status=TransactionStatus.SUCCESS,
            reference=f"job_payment_{job_id}_worker_{int(datetime.utcnow().timestamp())}",
            idempotency_key=idempotency_key,
            related_transaction_id=escrow_hold.id,
            description=f"Received payment for job: {job.title}",
            transaction_type=TransactionType.ESCROW_RELEASE.value,
        )
        self.db.add(worker_transaction)
        worker.wallet_balance += job_cost

        # Mark ESCROW_HOLD as SUCCESS (funds no longer pending, now released)
        escrow_hold.status = TransactionStatus.SUCCESS
        escrow_hold.updated_at = func.now()

        # Update payment record
        payment_query = select(Payment).where(Payment.job_id == job_id)
        payment_result = await self.db.execute(payment_query)
        payment = payment_result.scalar_one_or_none()
        if payment:
            payment.status = PaymentStatus.COMPLETED
            payment.completed_at = func.now()

        # Update job state to reflect completion with both confirmations
        job.completion_stage = CompletionStage.PAID
        job.status = JobStatus.COMPLETED
        job.completed_at = func.now()
        
        # Track request for idempotency
        if request_id:
            job.last_request_id = request_id
            job.last_request_at = datetime.utcnow()

        # Commit atomically
        await self.db.commit()
        
        # Auto-award job completion badges to the worker.
        # Never fail job completion if badge payload shape changes.
        try:
            badge_service = BadgeService(self.db)
            award_result = await badge_service.auto_award_badges(worker.id)
            awarded = (award_result or {}).get('awarded') or []

            if awarded:
                badge_names = [
                    b.get('name') or b.get('badge_name') or b.get('title') or 'Unknown badge'
                    for b in awarded
                    if isinstance(b, dict)
                ]
                logger.info(
                    f"Worker earned badges on job completion: {badge_names}",
                    worker_id=worker.id,
                    job_id=job_id
                )
        except Exception as badge_error:
            logger.warning(
                f"Badge award failed after job completion: {badge_error}",
                worker_id=worker.id,
                job_id=job_id
            )
        
        logger.info(
            "Job completion confirmed by both parties and funds released",
            job_id=job_id,
            amount=str(job_cost),
            worker_id=worker.id
        )

        # Broadcast and notify (outside transaction scope)
        try:
            await websocket_manager.broadcast_job_completed(
                job_id=job_id,
                job_title=job.title,
                worker_id=worker.id,
                employer_id=employer.id,
                amount=str(job_cost)
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast job completed event: {e}")

        # Send notifications
        notification_service = NotificationService(self.db)
        
        if user.role == UserRole.WORKER:
            await notification_service.create_notification(
                NotificationCreate(
                    user_id=employer.id,
                    title="Job Complete & Paid",
                    message=f"'{job.title}' has been completed by {worker.first_name} {worker.last_name}. Payment of ₦{job_cost} has been released.",
                    category=NotificationCategory.JOBS_AND_MATCHES,
                    action_screen="JobDetails",
                    action_payload={"job_id": job.id}
                )
            )
        elif user.role == UserRole.EMPLOYER:
            await notification_service.create_notification(
                NotificationCreate(
                    user_id=worker.id,
                    title="Job Completed & Paid",
                    message=f"'{job.title}' has been marked complete by the employer. Payment of ₦{job_cost} has been processed.",
                    category=NotificationCategory.JOBS_AND_MATCHES,
                    action_screen="JobDetails",
                    action_payload={"job_id": job.id}
                )
            )

        # Re-fetch the job to ensure the state is up-to-date before returning
        job = await _load_job_for_response(job_id)

        job = self._prepare_job_for_schema(job)
        job_schema = JobInDB.from_orm(job)
        job_schema.category_name = None
        job_schema = self._set_employer_data_safe(job_schema, job)
        job_schema.completion_status = self._get_completion_status(job)
        job_schema.attachments = [FileInDB.from_orm(attachment) for attachment in job.attachments]

        await self._invalidate_job_caches(job_id, job.employer_id)
        return job_schema
        
    async def publish_job(self, job_id: int, employer_id: int, request_id: Optional[str] = None) -> JobInDB:
        """
        Publish a job from DRAFT to OPEN status.
        Only the job owner (employer) can publish.
        """
        query = select(Job).where(Job.id == job_id).options(
            selectinload(Job.employer),
            selectinload(Job.attachments)
        )
        result = await self.db.execute(query)
        job = result.scalar_one_or_none()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )

        if job.employer_id != employer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to publish this job"
            )

        # Allow idempotent publish if already open
        if job.status == JobStatus.OPEN:
            job = self._prepare_job_for_schema(job)
            job_schema = JobInDB.from_orm(job)
            job_schema = self._set_employer_data_safe(job_schema, job)
            job_schema.attachments = [FileInDB.from_orm(a) for a in job.attachments]
            return job_schema
        if job.status != JobStatus.DRAFT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job cannot be published. Current status: {job.status}"
            )

        # Track request for idempotency
        if request_id:
            job.last_request_id = request_id
            job.last_request_at = func.now()

        job.status = JobStatus.OPEN
        job.updated_at = func.now()
        await self.db.commit()

        # Re-fetch and return
        query = select(Job).where(Job.id == job_id).options(
            selectinload(Job.employer),
            selectinload(Job.attachments)
        )
        result = await self.db.execute(query)
        job = result.scalar_one()

        job = self._prepare_job_for_schema(job)
        job_schema = JobInDB.from_orm(job)
        job_schema = self._set_employer_data_safe(job_schema, job)
        job_schema.attachments = [FileInDB.from_orm(a) for a in job.attachments]

        await self._invalidate_job_caches(job_id, employer_id)
        
        # Broadcast job published event
        try:
            await websocket_manager.broadcast_job_published(
                job_id=job_id,
                job_title=job.title,
                employer_id=employer_id,
                category=job.category_id if job.category_id else "General"
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast job published event: {e}")
        
        return job_schema

    async def unpublish_job(self, job_id: int, employer_id: int, request_id: Optional[str] = None) -> JobInDB:
        """
        Unpublish a job from OPEN back to DRAFT status.
        Only works if no workers have been hired yet.
        """
        query = select(Job).where(Job.id == job_id).options(
            selectinload(Job.employer),
            selectinload(Job.attachments)
        )
        result = await self.db.execute(query)
        job = result.scalar_one_or_none()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )

        if job.employer_id != employer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to unpublish this job"
            )

        # Can only unpublish OPEN jobs (not in progress or completed)
        if job.status not in [JobStatus.OPEN]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job cannot be unpublished from status: {job.status}"
            )

        # Track request for idempotency
        if request_id:
            job.last_request_id = request_id
            job.last_request_at = func.now()

        job.status = JobStatus.DRAFT
        job.updated_at = func.now()
        await self.db.commit()

        # Re-fetch and return
        query = select(Job).where(Job.id == job_id).options(
            selectinload(Job.employer),
            selectinload(Job.attachments)
        )
        result = await self.db.execute(query)
        job = result.scalar_one()

        job = self._prepare_job_for_schema(job)
        job_schema = JobInDB.from_orm(job)
        job_schema = self._set_employer_data_safe(job_schema, job)
        job_schema.attachments = [FileInDB.from_orm(a) for a in job.attachments]

        await self._invalidate_job_caches(job_id, employer_id)
        
        # Broadcast job unpublished event
        try:
            await websocket_manager.broadcast_job_unpublished(
                job_id=job_id,
                job_title=job.title,
                employer_id=employer_id
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast job unpublished event: {e}")
        
        return job_schema

    async def archive_job(self, job_id: int, employer_id: int, request_id: Optional[str] = None) -> JobInDB:
        """
        Archive a job (hide from listings with is_archived flag).
        Can be archived from OPEN or IN_PROGRESS states.
        Applications and contracts remain intact.
        Job status remains unchanged - archive is a separate concern.
        """
        query = select(Job).where(Job.id == job_id).options(
            selectinload(Job.employer),
            selectinload(Job.attachments)
        )
        result = await self.db.execute(query)
        job = result.scalar_one_or_none()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )

        if job.employer_id != employer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to archive this job"
            )

        # Can archive from OPEN or IN_PROGRESS states
        if job.status not in [JobStatus.OPEN, JobStatus.IN_PROGRESS]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job cannot be archived from status: {job.status.value}"
            )

        # Check if already archived
        if job.is_archived:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job is already archived"
            )

        # Track request for idempotency
        if request_id:
            job.last_request_id = request_id
            job.last_request_at = func.now()

        # Set archive flag instead of changing status
        job.is_archived = True
        job.updated_at = func.now()
        await self.db.commit()

        # Re-fetch and return
        query = select(Job).where(Job.id == job_id).options(
            selectinload(Job.employer),
            selectinload(Job.attachments)
        )
        result = await self.db.execute(query)
        job = result.scalar_one()

        job = self._prepare_job_for_schema(job)
        job_schema = JobInDB.from_orm(job)
        job_schema = self._set_employer_data_safe(job_schema, job)
        job_schema.attachments = [FileInDB.from_orm(a) for a in job.attachments]

        await self._invalidate_job_caches(job_id, employer_id)
        return job_schema

        await self._invalidate_job_caches(job_id, employer_id)
        
        # Broadcast job archived event
        try:
            await websocket_manager.broadcast_job_archived(
                job_id=job_id,
                job_title=job.title,
                employer_id=employer_id
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast job archived event: {e}")
        
        return job_schema

    async def unarchive_job(self, job_id: int, employer_id: int, request_id: Optional[str] = None) -> JobInDB:
        """
        Unarchive a job (restore to visible state by clearing is_archived flag).
        Restores visibility while preserving the current job status.
        """
        query = select(Job).where(Job.id == job_id).options(
            selectinload(Job.employer),
            selectinload(Job.attachments)
        )
        result = await self.db.execute(query)
        job = result.scalar_one_or_none()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )

        if job.employer_id != employer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to unarchive this job"
            )

        if not job.is_archived:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job is not archived"
            )

        # Track request for idempotency
        if request_id:
            job.last_request_id = request_id
            job.last_request_at = func.now()

        # Clear archive flag - job status remains unchanged
        job.is_archived = False
        job.updated_at = func.now()
        await self.db.commit()

        # Re-fetch and return
        query = select(Job).where(Job.id == job_id).options(
            selectinload(Job.employer),
            selectinload(Job.attachments)
        )
        result = await self.db.execute(query)
        job = result.scalar_one()

        job = self._prepare_job_for_schema(job)
        job_schema = JobInDB.from_orm(job)
        job_schema = self._set_employer_data_safe(job_schema, job)
        job_schema.attachments = [FileInDB.from_orm(a) for a in job.attachments]

        await self._invalidate_job_caches(job_id, employer_id)
        return job_schema
        
    async def delete_job(self, job_id: int, employer_id: int) -> bool:
        query = select(Job).where(Job.id == job_id)
        result = await self.db.execute(query)
        job = result.scalar_one_or_none()
        
        if not job:
            return False
        
        if job.employer_id != employer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this job"
            )

        await self.db.delete(job)
        await self.db.commit()

        await self._invalidate_job_caches(job_id, employer_id)
        return True

    async def search_jobs(
        self,
        query: str,
        skip: int = 0,
        limit: int = 10
    ) -> List[JobInDB]:
        search = f"%{query}%"
        db_query = (
            select(Job)
            .where(
                Job.title.ilike(search) |
                Job.description.ilike(search)
            )
            .options(
                selectinload(Job.attachments)
            )
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(db_query)
        jobs = result.scalars().all()

        jobs_schema = []
        for job in jobs:
            job = self._prepare_job_for_schema(job)
            job_schema = JobInDB.from_orm(job)
            job_schema.category_name = None
            job_schema = self._set_employer_data_safe(job_schema, job)
            job_schema.completion_status = self._get_completion_status(job)
            job_schema.all_reviews = await self._build_reviews_with_details(job)
            job_schema.attachments = [FileInDB.from_orm(attachment) for attachment in job.attachments]
            jobs_schema.append(job_schema)

        return jobs_schema

    async def get_worker_jobs(self, worker_id: int) -> List[JobInDB]:
        """Get jobs that a worker has accepted or is currently working on"""
        query = (
            select(Job)
            .join(JobApplication)
            .where(
                and_(
                    JobApplication.worker_id == worker_id,
                    JobApplication.status == ApplicationStatus.ACCEPTED,
                    Job.status.in_([JobStatus.IN_PROGRESS, JobStatus.COMPLETED])
                )
            )
            .options(
                selectinload(Job.employer),
                selectinload(Job.reviews).selectinload(Review.reviewer),
                selectinload(Job.reviews).selectinload(Review.reviewee),
                selectinload(Job.attachments),
                selectinload(Job.applications).selectinload(JobApplication.worker),
            )
            .order_by(Job.created_at.desc())
        )
        result = await self.db.execute(query)
        jobs = result.scalars().unique().all()

        jobs_schema = []
        for job in jobs:
            try:
                job = self._prepare_job_for_schema(job)
                job_schema = JobInDB.from_orm(job)
                job_schema.category_name = None
                
                # Safe access to employer fields with defaults
                if job.employer:
                    job_schema.employer_first_name = job.employer.first_name or "Unknown"
                    job_schema.employer_last_name = job.employer.last_name or ""
                    job_schema.employer_avatar_url = job.employer.avatar_url or None
                    job_schema.employer_phone = job.employer.phone or None
                    job_schema.employer_email = job.employer.email or None
                else:
                    job_schema.employer_first_name = "Unknown"
                    job_schema.employer_last_name = ""
                    job_schema.employer_avatar_url = None
                    job_schema.employer_phone = None
                    job_schema.employer_email = None
                
                job_schema.completion_status = self._get_completion_status(job)
                job_schema.all_reviews = await self._build_reviews_with_details(job)
                job_schema.attachments = [FileInDB.from_orm(attachment) for attachment in (job.attachments or [])]
                jobs_schema.append(job_schema)
            except Exception as e:
                logger.error(
                    "Error preparing job schema for worker",
                    job_id=job.id if job else None,
                    worker_id=worker_id,
                    error=str(e)
                )
                # Skip problematic jobs instead of crashing
                continue

        return jobs_schema

    async def get_applicants_for_job(self, job_id: int) -> List[JobApplicationInDB]:
        """Get all applications for a specific job."""
        query = (
            select(JobApplication)
            .where(JobApplication.job_id == job_id)
            .options(
                selectinload(JobApplication.worker)
            )
            .order_by(JobApplication.created_at.desc())
        )
        result = await self.db.execute(query)
        applications = result.scalars().all()
        
        return [JobApplicationInDB.from_orm(app) for app in applications]

    async def get_job_for_employer(self, job_id: int, employer_id: int) -> Optional[EmployerJobDetail]:
        query = (
            select(Job)
            .where(and_(Job.id == job_id, Job.employer_id == employer_id))
            .options(
                selectinload(Job.employer),
                selectinload(Job.applications),
                selectinload(Job.attachments),
                selectinload(Job.reviews).selectinload(Review.reviewer),
                selectinload(Job.reviews).selectinload(Review.reviewee),
            )
        )
        result = await self.db.execute(query)
        job = result.scalar_one_or_none()

        if not job:
            return None

        job = self._prepare_job_for_schema(job)

        # Manually construct the EmployerJobDetail to ensure all fields are correctly populated
        job_details = {
            **job.__dict__,
            "is_active": job.status in [JobStatus.OPEN, JobStatus.IN_PROGRESS],
            "applications_count": len(job.applications),
            "budget_formatted": (
                f"₦{job.job_price:,.2f}" if (job.payment_type == 'fixed_price' and job.job_price)
                else f"₦{job.hourly_rate:,.2f}/hr × {job.estimated_hours}hrs" if (job.payment_type == 'hourly_rate' and job.hourly_rate and job.estimated_hours)
                else "Price TBD"
            ),
            "skills_required": self._normalize_skills(job.tags),
            "attachments": [FileInDB.from_orm(attachment) for attachment in job.attachments],
            "category_name": self._format_category_name(job.category_id),
            "completion_status": self._get_completion_status(job),
            "all_reviews": await self._build_reviews_with_details(job),
            "location": job.location,
            "worker_completed": job.worker_completed,
            "employer_completed": job.employer_completed,
        }

        # Add employer details safely
        if job.employer:
            job_details["employer_first_name"] = job.employer.first_name
            job_details["employer_last_name"] = job.employer.last_name
            job_details["employer_avatar_url"] = job.employer.avatar_url
            job_details["employer_phone"] = job.employer.phone
            job_details["employer_email"] = job.employer.email

        return EmployerJobDetail.model_validate(job_details)

    async def get_job_for_worker(self, job_id: int, worker_id: int) -> Optional[WorkerJobDetail]:
        query = (
            select(Job)
            .where(Job.id == job_id)
            .options(
                selectinload(Job.employer),
                selectinload(Job.applications),
                selectinload(Job.attachments),
                selectinload(Job.reviews).selectinload(Review.reviewer),
                selectinload(Job.reviews).selectinload(Review.reviewee),
            )
        )
        result = await self.db.execute(query)
        job = result.scalar_one_or_none()

        if not job:
            return None

        job = self._prepare_job_for_schema(job)

        # Manually construct the WorkerJobDetail to ensure all fields are correctly populated
        job_details = {
            **job.__dict__,
            "is_active": job.status in [JobStatus.OPEN, JobStatus.IN_PROGRESS],
            "applications_count": len(job.applications),
            "budget_formatted": (
                f"₦{job.job_price:,.2f}" if (job.payment_type == 'fixed_price' and job.job_price)
                else f"₦{job.hourly_rate:,.2f}/hr × {job.estimated_hours}hrs" if (job.payment_type == 'hourly_rate' and job.hourly_rate and job.estimated_hours)
                else "Price TBD"
            ),
            "skills_required": self._normalize_skills(job.tags),
            "attachments": [FileInDB.from_orm(attachment) for attachment in job.attachments],
            "category_name": self._format_category_name(job.category_id),
            "completion_status": self._get_completion_status(job),
            "all_reviews": await self._build_reviews_with_details(job),
            "location": job.location,
            "worker_completed": job.worker_completed,
            "employer_completed": job.employer_completed,
        }

        # Add employer details safely
        if job.employer:
            job_details["employer_first_name"] = job.employer.first_name
            job_details["employer_last_name"] = job.employer.last_name
            job_details["employer_avatar_url"] = job.employer.avatar_url
            job_details["employer_phone"] = job.employer.phone
            job_details["employer_email"] = job.employer.email
            review_service = ReviewService(self.db)
            job_details["employer_review_stats"] = await review_service.get_user_review_stats(job.employer.id)
        
        # Add application-specific details for the worker
        application = await self.get_worker_application(job_id, worker_id)
        if application:
            job_details["application_status"] = application.status
            job_details["contract_status"] = application.contract_status
            job_details["boosted"] = application.boosted
            job_details["is_hired_worker"] = (
                job.status == JobStatus.IN_PROGRESS and application.status == ApplicationStatus.ACCEPTED
            )

        return WorkerJobDetail.model_validate(job_details)

    async def get_worker_active_contracts(self, worker_id: int) -> List[JobInDB]:
        """Get active contracts for a worker."""
        query = (
            select(Job)
            .join(JobApplication)
            .where(
                and_(
                    JobApplication.worker_id == worker_id,
                    JobApplication.status == ApplicationStatus.ACCEPTED,
                    Job.status == JobStatus.IN_PROGRESS
                )
            )
            .options(
                selectinload(Job.employer),
                selectinload(Job.attachments),
            )
            .order_by(Job.created_at.desc())
        )
        result = await self.db.execute(query)
        jobs = result.scalars().unique().all()

        jobs_schema = []
        for job in jobs:
            job = self._prepare_job_for_schema(job)
            job_schema = JobInDB.from_orm(job)
            job_schema.category_name = None
            job_schema = self._set_employer_data_safe(job_schema, job)
            job_schema.attachments = [FileInDB.from_orm(attachment) for attachment in job.attachments]
            jobs_schema.append(job_schema)

        return jobs_schema

    async def get_application_by_id(self, application_id: int) -> Optional[JobApplication]:
        query = select(JobApplication).where(JobApplication.id == application_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_applicant_by_application_id(self, application_id: int) -> Optional[Applicant]:
        query = (
            select(JobApplication)
            .where(JobApplication.id == application_id)
            .options(selectinload(JobApplication.worker))
        )
        result = await self.db.execute(query)
        application = result.scalar_one_or_none()

        if application and application.worker:
            return Applicant(
                id=application.worker.id,
                first_name=application.worker.first_name,
                last_name=application.worker.last_name,
                headline=application.worker.headline,
                avatar_url=application.worker.avatar_url,
                rating=application.worker.rating,
                created_at=application.created_at,
                cover_letter=application.cover_letter,
                proposal=application.proposal,
            )
        return None

    async def get_applicants_by_job_id(self, job_id: int, sort_by_boosted: bool = False) -> List[Applicant]:
        query = (
            select(JobApplication)
            .where(JobApplication.job_id == job_id)
            .options(selectinload(JobApplication.worker))
        )
        if sort_by_boosted:
            query = query.order_by(JobApplication.boosted.desc(), JobApplication.created_at.desc())
        else:
            query = query.order_by(JobApplication.created_at.desc())
            
        result = await self.db.execute(query)
        applications = result.scalars().all()

        applicant_details = []
        for app in applications:
            if app.worker:
                applicant_details.append(
                    Applicant(
                        id=app.worker.id,
                        first_name=app.worker.first_name,
                        last_name=app.worker.last_name,
                        headline=app.worker.headline,
                        avatar_url=app.worker.avatar_url,
                        rating=app.worker.rating,
                        created_at=app.created_at,
                        cover_letter=app.cover_letter,
                        proposal=app.proposal,
                    )
                )
        return applicant_details

    async def boost_job(self, job_id: int, employer_id: int) -> dict:
        """
        Boost a job to increase visibility in search results.
        
        Cost: ₦999 for 7 days
        Effect: Job appears first in search results
        
        Returns:
            dict with boost details and cost
        """
        BOOST_COST = 999.0
        BOOST_DURATION_DAYS = 7
        
        # Get the job
        job = await self.db.get(Job, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        # Verify ownership
        if job.employer_id != employer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to boost this job"
            )
        
        # Get the employer to check wallet balance
        employer = await self.db.get(User, employer_id)
        if not employer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employer not found"
            )
        
        # Check wallet balance
        if employer.wallet_balance < BOOST_COST:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient funds. You need ₦{BOOST_COST} to boost this job."
            )
        
        # If job is already boosted, extend the boost instead of creating a duplicate
        now = datetime.now(timezone.utc)
        if job.boost_active and job.boost_expires_at and job.boost_expires_at > now:
            # Extend the existing boost
            job.boost_expires_at = job.boost_expires_at + timedelta(days=BOOST_DURATION_DAYS)
        else:
            # Create new boost
            job.boost_active = True
            job.boost_expires_at = now + timedelta(days=BOOST_DURATION_DAYS)
        
        # Deduct cost from employer wallet
        transaction_service = TransactionService(self.db)
        timestamp = int(datetime.utcnow().timestamp())
        
        await transaction_service.create_transaction(
            user_id=employer_id,
            amount=-BOOST_COST,
            transaction_type=TransactionType.BOOST.value,
            reference=f"job_boost_{job.id}_{timestamp}",
            description=f"Job boost for: {job.title}"
        )
        
        # Create boost transaction log
        from ..models.boost_transaction import BoostTransaction, BoostType
        boost_transaction = BoostTransaction(
            user_id=employer_id,
            boost_type=BoostType.JOB,
            reference_id=job_id,
            cost=BOOST_COST,
            duration_days=BOOST_DURATION_DAYS,
            expires_at=job.boost_expires_at
        )
        self.db.add(boost_transaction)
        
        # Commit all changes
        await self.db.commit()
        await self.db.refresh(job)
        
        # Invalidate caches
        await self._invalidate_job_caches(job_id, employer_id)
        
        return {
            "success": True,
            "boosted": True,
            "boost_duration_days": BOOST_DURATION_DAYS,
            "boost_expires_at": job.boost_expires_at.isoformat(),
            "cost": BOOST_COST,
            "message": f"Job boosted successfully for {BOOST_DURATION_DAYS} days!"
        }
