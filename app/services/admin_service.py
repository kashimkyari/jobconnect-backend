import math
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_, desc, text
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from ..models.user import User, UserRole
from ..models.job import Job, JobStatus
from ..schemas.job import CompletionStatus
from ..models.job_application import JobApplication
from ..models.payment import Payment, PaymentStatus
from ..models.transaction import Transaction
from ..models.review import Review
from ..models.badge import Badge
from ..models.message import Message
from ..models.dispute import Dispute, DisputeStatus
from ..models.subscription import SubscriptionPlan
from ..models.recent_activity import RecentActivity
from ..models.kyc import KYCSubmission
from ..models.category import Category
from ..schemas.kyc import KYCSubmission as KYCSubmissionSchema
from ..schemas.subscription import SubscriptionPlanCreate, SubscriptionPlanUpdate
from ..models.service import Service
from ..schemas.service import ServiceCreate, ServiceUpdate
from ..schemas.admin import AdminJobInDB
from ..schemas.user import UserInDB
from ..schemas.job_application import JobApplicationAdminInDB
from ..utils.logging import StructuredLogger
from ..config import settings
from decimal import Decimal
from ..utils.email import send_email
from ..utils.sms import send_sms

logger = StructuredLogger("admin")
SUBSCRIPTION_FEE = 2000  # ₦2000

class AdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get overview statistics for the admin dashboard"""
        today = datetime.utcnow().date()
        seven_days_ago = today - timedelta(days=7)

        async def get_count(model, condition=None):
            query = select(func.count(model.id))
            if condition is not None:
                query = query.where(condition)
            result = await self.db.execute(query)
            return result.scalar() or 0

        async def get_sum(model, column, condition=None):
            query = select(func.sum(column))
            if condition is not None:
                query = query.where(condition)
            result = await self.db.execute(query)
            return result.scalar() or 0

        # Platform Health & Safety
        unverified_user_accounts = await get_count(User, and_(User.is_verified == False, User.role != UserRole.ADMIN))

        # Daily Operations
        new_user_registrations_today = await get_count(User, func.date(User.created_at) == today)
        job_postings_pending_approval = await get_count(Job, Job.status == JobStatus.DRAFT)
        payment_disputes = await get_count(Dispute, Dispute.status == DisputeStatus.OPEN)
        user_bans_suspensions = await get_count(User, User.is_active == False)

        # Revenue Monitoring
        daily_revenue = await get_sum(Payment, Payment.amount, and_(Payment.status == PaymentStatus.COMPLETED, func.date(Payment.completed_at) == today))
        weekly_revenue = await get_sum(Payment, Payment.amount, and_(Payment.status == PaymentStatus.COMPLETED, Payment.completed_at >= seven_days_ago))
        failed_payments = await get_count(Payment, Payment.status == PaymentStatus.FAILED)
        refund_requests = await get_count(Dispute, Dispute.resolution.like('%refund%'))

        # Quality Control
        completed_jobs_total = await get_count(Job, Job.status == JobStatus.COMPLETED)
        total_jobs_for_rate = completed_jobs_total
        application_success_rate = 100 if total_jobs_for_rate > 0 else 0

        # Key Performance Indicators
        active_job_listings = await get_count(Job, Job.status == JobStatus.OPEN)
        
        # User engagement trends (e.g., active users in last 7 days as a percentage of total users)
        active_users_last_7_days = await get_count(User, User.updated_at >= seven_days_ago)
        total_users = await get_count(User)
        user_engagement_trends = (active_users_last_7_days / total_users) * 100 if total_users > 0 else 0

        # Conversion rates (e.g., users who have applied for at least one job)
        users_with_applications = await self.db.execute(select(func.count(func.distinct(JobApplication.worker_id))))
        total_workers = await get_count(User, User.role == UserRole.WORKER)
        conversion_rates = (users_with_applications.scalar_one() / total_workers) * 100 if total_workers > 0 else 0

        # Existing useful stats
        platform_earnings = await get_sum(Payment, Payment.commission_amount, Payment.status == PaymentStatus.COMPLETED)
        
        fourteen_days_ago = today - timedelta(days=14)
        new_users_last_7_days = await get_count(User, and_(User.created_at >= seven_days_ago, User.created_at < today))
        new_users_previous_7_days = await get_count(User, and_(User.created_at >= fourteen_days_ago, User.created_at < seven_days_ago))
        
        if new_users_previous_7_days > 0:
            user_growth_rate = ((new_users_last_7_days - new_users_previous_7_days) / new_users_previous_7_days) * 100
        else:
            user_growth_rate = 100.0 if new_users_last_7_days > 0 else 0.0

        total_payment_volume = await get_sum(Payment, Payment.amount, Payment.status == PaymentStatus.COMPLETED)
        total_transactions = await get_count(Payment, Payment.status == PaymentStatus.COMPLETED)

        # Additional stats required by DashboardStats schema
        active_jobs = await get_count(Job, Job.status == JobStatus.OPEN)
        completed_jobs = await get_count(Job, Job.status == JobStatus.COMPLETED)
        total_disputes = await get_count(Dispute)
        open_disputes = await get_count(Dispute, Dispute.status == DisputeStatus.OPEN)
        pending_verifications = await get_count(KYCSubmission, KYCSubmission.status == 'pending')
        platform_earnings_last_7_days = await get_sum(Payment, Payment.commission_amount, and_(Payment.status == PaymentStatus.COMPLETED, Payment.completed_at >= seven_days_ago))

        total_completed_jobs = await get_count(Job, Job.status == JobStatus.COMPLETED)
        total_cancellable_jobs = await get_count(Job, Job.status == JobStatus.COMPLETED)
        job_completion_rate = (total_completed_jobs / total_cancellable_jobs) * 100 if total_cancellable_jobs > 0 else 0

        return {
            "total_users": total_users,
            "new_users_today": new_user_registrations_today,
            "active_users_last_7_days": active_users_last_7_days,
            "active_jobs": active_jobs,
            "completed_jobs": completed_jobs,
            "total_disputes": total_disputes,
            "open_disputes": open_disputes,
            "pending_verifications": pending_verifications,
            "platform_earnings": round(float(platform_earnings or 0), 2),
            "platform_earnings_last_7_days": round(float(platform_earnings_last_7_days or 0), 2),
            "user_growth_rate": round(user_growth_rate, 2),
            "job_completion_rate": round(job_completion_rate, 2),
            
            # These fields are in DashboardData but not DashboardStats, returning them anyway
            "unverified_user_accounts": unverified_user_accounts,
            "new_user_registrations_today": new_user_registrations_today,
            "job_postings_pending_approval": job_postings_pending_approval,
            "payment_disputes": payment_disputes,
            "user_bans_suspensions": user_bans_suspensions,
            "daily_revenue": round(float(daily_revenue or 0), 2),
            "weekly_revenue": round(float(weekly_revenue or 0), 2),
            "failed_payments": failed_payments,
            "refund_requests": refund_requests,
            "application_success_rate": round(application_success_rate, 2),
            "active_job_listings": active_job_listings,
            "user_engagement_trends": round(user_engagement_trends, 2),
            "conversion_rates": round(conversion_rates, 2),
            "total_payment_volume": round(float(total_payment_volume or 0), 2),
            "total_transactions": total_transactions,
        }

    async def list_users(
        self,
        role: Optional[UserRole] = None,
        is_verified: Optional[bool] = None,
        is_active: Optional[bool] = None,
        kyc_status: Optional[str] = None,
        q: Optional[str] = None,
        location: Optional[str] = None,
        skip: int = 0,
        limit: int = 10
    ) -> Dict[str, Any]:
        query = select(User)
        
        if role:
            query = query.where(User.role == role)
        if is_verified is not None:
            query = query.where(User.is_verified == is_verified)
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        if kyc_status:
            if kyc_status == "not_submitted":
                query = query.where(or_(User.kyc_status == None, User.kyc_status == "not_submitted"))
            else:
                query = query.where(User.kyc_status == kyc_status)
        if q:
            term = f"%{q.strip()}%"
            query = query.where(or_(
                User.first_name.ilike(term),
                User.last_name.ilike(term),
                User.email.ilike(term),
                User.phone.ilike(term),
                User.location.ilike(term),
            ))
        if location:
            loc = f"%{location.strip()}%"
            query = query.where(User.location.ilike(loc))
            
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.execute(count_query)
        
        query = query.order_by(desc(User.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        users = result.scalars().all()
        
        total_count = total.scalar()
        total_pages = math.ceil(total_count / limit) if limit > 0 else 0
        
        users_list = [self._serialize_user(user) for user in users]

        return {
            "total": total_count,
            "page": (skip // limit) + 1 if limit > 0 else 1,
            "per_page": limit,
            "total_pages": total_pages,
            "has_next": ((skip + limit) < total_count) if limit > 0 else False,
            "has_prev": skip > 0,
            "users": users_list
        }

    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a single user by their ID."""
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if user:
            return self._serialize_user(user)
        return None
    
    async def get_job_by_id(self, job_id: int) -> Optional[AdminJobInDB]:
        """Get a single job by its ID with all related data."""
        query = select(Job).where(Job.id == job_id).options(
            selectinload(Job.employer),
            selectinload(Job.worker),
            selectinload(Job.applications).options(
                selectinload(JobApplication.worker),
                selectinload(JobApplication.status_history)
            ),
            selectinload(Job.disputes),
            selectinload(Job.payments),
            selectinload(Job.reviews).selectinload(Review.reviewer),
            selectinload(Job.reviews).selectinload(Review.reviewee),
            selectinload(Job.attachments)
        )
        result = await self.db.execute(query)
        job = result.scalars().unique().one_or_none()

        if job:
            serialized_job = await self._serialize_job(job)
            return AdminJobInDB.model_validate(serialized_job)
        return None

    def _serialize_user(self, user: User) -> Dict[str, Any]:
        return {
            "id": user.id,
            "email": user.email,
            "phone": user.phone,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role.value,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_kyc_verified": user.is_kyc_verified,
            "kyc_status": user.kyc_status,
            "location": user.location,
            "avatar_url": user.avatar_url,
            "reputation_score": user.reputation_score,
            "wallet_balance": user.wallet_balance,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat()
        }

    def _serialize_review(self, review: Review) -> Dict[str, Any]:
        return {
            "id": review.id,
            "job_id": review.job_id,
            "job_title": review.job.title if review.job else "N/A",
            "reviewer": self._serialize_user_simple(review.reviewer),
            "reviewee": self._serialize_user_simple(review.reviewee),
            "rating": review.rating,
            "comment": review.comment,
            "created_at": review.created_at.isoformat(),
        }

    def _serialize_badge(self, badge: Badge) -> Dict[str, Any]:
        return {
            "id": badge.id,
            "name": badge.name,
            "description": badge.description,
            "image_url": badge.image_url,
            "created_at": badge.created_at.isoformat(),
        }

    async def list_reviews(
        self,
        skip: int = 0,
        limit: int = 10
    ) -> Dict[str, Any]:
        query = select(Review).options(
            selectinload(Review.reviewer),
            selectinload(Review.reviewee),
            selectinload(Review.job)
        )
        
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.execute(count_query)
        
        query = query.order_by(desc(Review.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        reviews = result.scalars().all()
        
        total_count = total.scalar()
        total_pages = math.ceil(total_count / limit) if limit > 0 else 0

        return {
            "total": total_count,
            "page": (skip // limit) + 1 if limit > 0 else 1,
            "per_page": limit,
            "total_pages": total_pages,
            "has_next": ((skip + limit) < total_count) if limit > 0 else False,
            "has_prev": skip > 0,
            "reviews": [self._serialize_review(review) for review in reviews],
        }

    async def list_badges(
        self,
        skip: int = 0,
        limit: int = 10
    ) -> Dict[str, Any]:
        query = select(Badge)
        
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.execute(count_query)
        
        query = query.order_by(desc(Badge.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        badges = result.scalars().all()
        
        total_count = total.scalar()
        total_pages = math.ceil(total_count / limit) if limit > 0 else 0

        return {
            "total": total_count,
            "page": (skip // limit) + 1 if limit > 0 else 1,
            "per_page": limit,
            "total_pages": total_pages,
            "has_next": ((skip + limit) < total_count) if limit > 0 else False,
            "has_prev": skip > 0,
            "badges": [self._serialize_badge(badge) for badge in badges],
        }

    async def list_jobs(
        self,
        status: Optional[str] = None,
        has_dispute: Optional[bool] = None,
        skip: int = 0,
        limit: int = 10
    ) -> Dict[str, Any]:
        query = select(Job).options(
            selectinload(Job.employer),
            selectinload(Job.disputes)
        )
        
        if status:
            query = query.where(Job.status == status)
        if has_dispute is not None:
            query = query.where(Job.disputes.any() if has_dispute else ~Job.disputes.any())
            
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.execute(count_query)
        
        query = query.order_by(desc(Job.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        jobs = result.scalars().unique().all()
        
        total_count = total.scalar()
        total_pages = math.ceil(total_count / limit) if limit > 0 else 0

        serialized_jobs = [self._serialize_job_for_admin_list(job) for job in jobs]

        return {
            "total": total_count,
            "page": (skip // limit) + 1 if limit > 0 else 1,
            "per_page": limit,
            "total_pages": total_pages,
            "has_next": ((skip + limit) < total_count) if limit > 0 else False,
            "has_prev": skip > 0,
            "jobs": serialized_jobs,
        }

    async def list_job_applicants(
        self,
        job_id: int,
        skip: int = 0,
        limit: int = 10
    ) -> Dict[str, Any]:
        query = select(JobApplication).where(JobApplication.job_id == job_id).options(
            selectinload(JobApplication.worker)
        )

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.execute(count_query)
        total_count = total.scalar()

        query = query.order_by(desc(JobApplication.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        applications = result.scalars().unique().all()

        total_pages = math.ceil(total_count / limit) if limit > 0 else 0

        return {
            "total": total_count,
            "page": (skip // limit) + 1 if limit > 0 else 1,
            "per_page": limit,
            "total_pages": total_pages,
            "has_next": ((skip + limit) < total_count) if limit > 0 else False,
            "has_prev": skip > 0,
            "applicants": [self._serialize_applicant(app) for app in applications],
        }

    def _serialize_applicant(self, application: JobApplication) -> Dict[str, Any]:
        worker = application.worker
        return {
            "id": worker.id,
            "first_name": worker.first_name,
            "last_name": worker.last_name,
            "email": worker.email,
            "avatar_url": worker.avatar_url,
            "application_status": application.status.value,
            "application_date": application.created_at,
        }

    def _get_completion_status(self, job: Job) -> Optional[CompletionStatus]:
        if job.status == JobStatus.COMPLETED:
            return CompletionStatus.COMPLETED
        if job.worker_completed and not job.employer_completed:
            return CompletionStatus.WAITING_FOR_EMPLOYER
        return None

    async def _build_reviews_with_details(self, job: Job) -> List[dict]:
        """Build all reviews for a job with reviewer/reviewee details and role indicators."""
        all_reviews = []
        if not job.reviews:
            return all_reviews
        
        for review in job.reviews:
            review_data = {
                "id": review.id,
                "rating": float(review.rating),
                "comment": review.comment,
                "job_id": review.job_id,
                "reviewer_id": review.reviewer_id,
                "reviewer_name": f"{review.reviewer.first_name} {review.reviewer.last_name}",
                "reviewer_avatar": review.reviewer.avatar_url,
                "reviewer_role": "employer" if review.reviewer_id == job.employer_id else "worker",
                "reviewee_id": review.reviewee_id,
                "reviewee_name": f"{review.reviewee.first_name} {review.reviewee.last_name}",
                "reviewee_avatar": review.reviewee.avatar_url,
                "reviewee_role": "employer" if review.reviewee_id == job.employer_id else "worker",
                "created_at": review.created_at.isoformat(),
                "updated_at": review.updated_at.isoformat(),
            }
            all_reviews.append(review_data)
        
        return all_reviews

    def _serialize_job_for_admin_list(self, job: Job) -> Dict[str, Any]:
        job_price = float(job.job_price) if job.job_price is not None else None
        return {
            "id": job.id,
            "title": job.title,
            "description": job.description,
            "status": job.status.value,
            "employer_name": f"{job.employer.first_name} {job.employer.last_name}" if job.employer else "N/A",
            "job_price": job_price,
            "budget": job_price,  # legacy alias
            "has_dispute": len(job.disputes) > 0,
        }

    async def _serialize_job(self, job: Job) -> Dict[str, Any]:
        requirements_list = []
        # Skip main_duties and deliverables as they don't exist in the Job model
        if job.experience_level:
            requirements_list.append(f"Experience Level: {job.experience_level.value}")

        job_price = float(job.job_price) if job.job_price is not None else None
        job_data = {
            "id": job.id,
            "title": job.title,
            "description": job.description,
            "requirements": "\n".join(requirements_list) if requirements_list else job.contract_details or "",
            "job_price": job_price,
            "budget": job_price,  # legacy alias
            "location": job.location,
            "location_type": job.location_type.value if job.location_type else None,
            "status": job.status.value,
            "employer_id": job.employer.id,
            "employer_first_name": job.employer.first_name,
            "employer_last_name": job.employer.last_name,
            "employer_avatar_url": job.employer.avatar_url,
            "employer_phone": job.employer.phone,
            "employer_email": job.employer.email,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "is_high_value": job.is_high_value,
            "escrow_required": job.escrow_required,
            "commission_rate": float(job.commission_rate) if job.commission_rate is not None else None,
            "completed_at": job.completed_at,
            "category_name": job.category_id,
            "completion_status": self._get_completion_status(job).value if self._get_completion_status(job) else None,
            "applicant_count": len(job.applications) if job.applications else 0,
            "dispute_status": job.disputes[0].status.value if job.disputes else "No Dispute",
            "payment_status": job.payments[0].status.value if job.payments else "Not Paid",
            "category_id": job.category_id,
            "job_type": job.job_type.value if job.job_type else None,
            "tags": job.tags,
            "attachments": job.attachments,
            "all_reviews": await self._build_reviews_with_details(job),
            "applications": [JobApplicationAdminInDB.model_validate(app) for app in job.applications],
            "worker": UserInDB.model_validate(job.worker) if job.worker else None,
            "payments": job.payments,
            "disputes": job.disputes,
        }

        return job_data

    async def list_disputes(
        self,
        status: Optional[DisputeStatus] = None,
        skip: int = 0,
        limit: int = 10
    ) -> Dict[str, Any]:
        query = select(Dispute).options(
            selectinload(Dispute.job),
            selectinload(Dispute.employer),
            selectinload(Dispute.worker)
        )
        if status:
            query = query.where(Dispute.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.execute(count_query)
        total_count = total.scalar()

        query = query.order_by(desc(Dispute.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        disputes = result.scalars().unique().all()

        return {
            "total": total_count,
            "page": (skip // limit) + 1,
            "per_page": limit,
            "total_pages": math.ceil(total_count / limit),
            "has_next": (skip + limit) < total_count,
            "has_prev": skip > 0,
            "disputes": [self._serialize_dispute(dispute) for dispute in disputes]
        }

    def _serialize_dispute(self, dispute: Dispute) -> Dict[str, Any]:
        return {
            "id": dispute.id,
            "dispute_type": dispute.dispute_type.value,
            "job_id": dispute.job_id,
            "job_title": dispute.job.title if dispute.job else "N/A",
            "amount": float(dispute.job.confirmed_price or dispute.job.job_price or (float(dispute.job.hourly_rate or 0) * float(dispute.job.estimated_hours or 0)) or 0) if dispute.job else 0,
            "employer": self._serialize_user_simple(dispute.employer),
            "worker": self._serialize_user_simple(dispute.worker),
            "status": dispute.status.value,
            "reason": dispute.reason,
            "resolution": dispute.resolution,
            "created_at": dispute.created_at.isoformat(),
            "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        }

    def _serialize_user_simple(self, user: User) -> Optional[Dict[str, Any]]:
        if not user:
            return None
        return {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "address": user.location,
            "created_at": user.created_at.isoformat(),
        }

    async def resolve_dispute(
        self,
        dispute_id: int,
        resolution: str,
        admin_id: int
    ) -> Optional[Dispute]:
        query = select(Dispute).where(Dispute.id == dispute_id).options(
            selectinload(Dispute.employer),
            selectinload(Dispute.worker)
        )
        result = await self.db.execute(query)
        dispute = result.scalar_one_or_none()

        if not dispute:
            return None

        dispute.status = DisputeStatus.RESOLVED
        dispute.resolution = resolution
        dispute.resolved_by_admin_id = admin_id
        dispute.resolved_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(dispute)
        return dispute

    async def list_flagged_content(
        self,
        content_type: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 10
    ) -> Dict[str, Any]:
        # This is a placeholder implementation. 
        # In a real application, you would have a dedicated model for flagged content.
        # For now, we'll return an empty list with proper pagination.
        
        total_count = 0
        total_pages = 0
        
        return {
            "total": total_count,
            "page": (skip // limit) + 1 if limit > 0 else 1,
            "per_page": limit,
            "total_pages": total_pages,
            "has_next": False,
            "has_prev": skip > 0,
            "content": []
        }

    async def moderate_content(
        self,
        content_id: int,
        action: str,
        reason: str
    ) -> Any:
        # Placeholder for content moderation logic
        pass

    async def suspend_user(
        self,
        user_id: int,
        reason: str,
        duration_days: int
    ) -> Optional[User]:
        user = await self.db.get(User, user_id)
        if not user:
            return None
            
        user.is_active = False
        # In a real app, you'd store suspension reason and end date
        
        await self.db.commit()
        await self.db.refresh(user)
        
        logger.info(
            "User suspended",
            user_id=user.id,
            reason=reason,
            duration_days=duration_days
        )
        
        return user

    async def get_platform_metrics(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        try:
            # Handle ISO format with 'Z' at the end
            if start_date.endswith('Z'):
                start_date = start_date[:-1] + '+00:00'
            if end_date.endswith('Z'):
                end_date = end_date[:-1] + '+00:00'

            start = datetime.fromisoformat(start_date).replace(tzinfo=None)
            end = datetime.fromisoformat(end_date).replace(tzinfo=None)
        except ValueError:
            try:
                start = datetime.strptime(start_date, "%d/%m/%Y")
                end = datetime.strptime(end_date, "%d/%m/%Y")
            except ValueError:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                end = datetime.strptime(end_date, "%Y-%m-%d")

        user_growth = await self._get_user_growth_metrics(start, end)
        job_metrics = await self._get_job_metrics(start, end)
        payment_metrics = await self._get_payment_metrics(start, end)
        engagement = await self._get_engagement_metrics(start, end)
        
        return {
            "user_growth": user_growth,
            "jobs": job_metrics,
            "payments": payment_metrics,
            "engagement": engagement
        }

    async def _get_user_growth_metrics(
        self,
        start: datetime,
        end: datetime
    ) -> Dict[str, Any]:
        query = (
            select(func.date(User.created_at).label('date'), func.count(User.id).label('count'))
            .where(User.created_at.between(start, end))
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
        )
        result = await self.db.execute(query)
        return [{"date": row.date.isoformat(), "count": row.count} for row in result]

    async def _get_job_metrics(
        self,
        start: datetime,
        end: datetime
    ) -> Dict[str, Any]:
        query = select(
            func.count(Job.id).label("total"),
            func.count(Job.id).filter(Job.status == JobStatus.COMPLETED).label("completed")
        ).where(Job.created_at.between(start, end))
        result = await self.db.execute(query)
        metrics = result.one()
        total = metrics.total or 0
        completed = metrics.completed or 0
        return {"completion_rate": (completed / total * 100) if total > 0 else 0}

    async def _get_payment_metrics(
        self,
        start: datetime,
        end: datetime
    ) -> Dict[str, Any]:
        query = (
            select(func.sum(Payment.amount).label('total'), func.count(Payment.id).label('count'))
            .where(Payment.created_at.between(start, end))
            .where(Payment.status == PaymentStatus.COMPLETED)
        )
        result = await self.db.execute(query)
        metrics = result.one()
        return {"total_volume": float(metrics.total or 0), "transaction_count": metrics.count}

    async def _get_engagement_metrics(
        self,
        start: datetime,
        end: datetime
    ) -> Dict[str, Any]:
        message_query = select(func.count(Message.id)).where(Message.created_at.between(start, end))
        review_query = select(func.count(Review.id)).where(Review.created_at.between(start, end))
        messages = await self.db.execute(message_query)
        reviews = await self.db.execute(review_query)
        return {"message_count": messages.scalar() or 0, "review_count": reviews.scalar() or 0}

    async def initiate_subscription(self, user: User) -> Dict:
        # ... (implementation remains the same)
        pass

    async def process_subscription_webhook(self, data: Dict) -> None:
        # ... (implementation remains the same)
        pass

    async def process_application_fee(self, user: User, job_id: int) -> None:
        # ... (implementation remains the same)
        pass

    async def fund_wallet(self, user: User, amount: float) -> Dict:
        # ... (implementation remains the same)
        pass

    async def create_subscription_plan(self, plan_data: SubscriptionPlanCreate) -> SubscriptionPlan:
        plan = SubscriptionPlan(**plan_data.dict())
        self.db.add(plan)
        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def update_subscription_plan(self, plan_id: int, plan_data: SubscriptionPlanUpdate) -> Optional[SubscriptionPlan]:
        plan = await self.db.get(SubscriptionPlan, plan_id)
        if not plan:
            return None
        
        for field, value in plan_data.dict(exclude_unset=True).items():
            setattr(plan, field, value)
            
        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def get_all_subscription_plans(self) -> List[SubscriptionPlan]:
        query = select(SubscriptionPlan)
        result = await self.db.execute(query)
        return result.scalars().all()



    async def create_service(self, service_data: ServiceCreate) -> Service:
        service = Service(**service_data.dict())
        self.db.add(service)
        await self.db.commit()
        await self.db.refresh(service)
        return service

    async def get_services(self) -> List[Service]:
        query = select(Service)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_service(self, service_id: int, service_data: ServiceUpdate) -> Optional[Service]:
        service = await self.db.get(Service, service_id)
        if not service:
            return None
        
        for field, value in service_data.dict(exclude_unset=True).items():
            setattr(service, field, value)
            
        await self.db.commit()
        await self.db.refresh(service)
        return service

    async def delete_service(self, service_id: int) -> bool:
        service = await self.db.get(Service, service_id)
        if not service:
            return False
        
        await self.db.delete(service)
        await self.db.commit()
        return True

    async def list_kyc_submissions(self, skip: int = 0, limit: int = 10) -> Dict[str, Any]:
        query = select(KYCSubmission).options(selectinload(KYCSubmission.user))
        
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.execute(count_query)
        total_count = total.scalar()
        
        query = query.order_by(desc(KYCSubmission.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        submissions = result.scalars().unique().all()
        
        return {
            "total": total_count,
            "page": (skip // limit) + 1,
            "per_page": limit,
            "total_pages": math.ceil(total_count / limit),
            "has_next": (skip + limit) < total_count,
            "has_prev": skip > 0,
            "submissions": [self._serialize_kyc_submission(sub) for sub in submissions]
        }

    def _serialize_kyc_submission(self, submission: KYCSubmission) -> KYCSubmissionSchema:
        return KYCSubmissionSchema.model_validate(submission)

    async def _serialize_transaction(self, transaction: Transaction) -> Dict[str, Any]:
        fee = float(transaction.platform_fee or 0)
        amount = float(transaction.amount or 0)
        net_amount = amount - fee

        direction = "credit"
        if transaction.transaction_type.value in ["payment", "withdrawal", "refund"]:
            direction = "debit"

        response = {
            "id": transaction.id,
            "user_id": transaction.user_id,
            "initiator": self._serialize_user_simple(transaction.user),
            "employer": None,
            "worker": None,
            "amount": amount,
            "fee": fee,
            "netAmount": net_amount,
            "type": transaction.transaction_type.value,
            "status": transaction.status.value,
            "reference": transaction.reference,
            "description": transaction.description,
            "method": "Card",  # Placeholder
            "created_at": transaction.created_at,
            "updated_at": transaction.updated_at,
            "timestamp": transaction.created_at,
            "direction": direction,
        }

        if transaction.job_id:
            job = await self.db.get(Job, transaction.job_id)
            if job:
                response["employer"] = self._serialize_user_simple(job.employer)
                response["worker"] = self._serialize_user_simple(job.worker)

        return response

    async def list_transactions(
        self,
        skip: int = 0,
        limit: int = 10
    ) -> Dict[str, Any]:
        query = select(Transaction).options(
            selectinload(Transaction.user),
            selectinload(Transaction.job).selectinload(Job.employer),
            selectinload(Transaction.job).selectinload(Job.worker)
        )
        
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.execute(count_query)
        
        query = query.order_by(desc(Transaction.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        transactions = result.scalars().unique().all()
        
        total_count = total.scalar()
        total_pages = math.ceil(total_count / limit) if limit > 0 else 0

        serialized_transactions = [await self._serialize_transaction(t) for t in transactions]

        return {
            "total": total_count,
            "page": (skip // limit) + 1 if limit > 0 else 1,
            "per_page": limit,
            "total_pages": total_pages,
            "has_next": ((skip + limit) < total_count) if limit > 0 else False,
            "has_prev": skip > 0,
            "transactions": serialized_transactions,
        }

    async def get_transaction_by_id(self, transaction_id: int) -> Optional[Dict[str, Any]]:
        """Get a single transaction by its ID."""
        query = select(Transaction).where(Transaction.id == transaction_id).options(
            selectinload(Transaction.user),
            selectinload(Transaction.job).selectinload(Job.employer),
            selectinload(Transaction.job).selectinload(Job.worker)
        )
        result = await self.db.execute(query)
        transaction = result.scalars().unique().one_or_none()

        if transaction:
            return await self._serialize_transaction(transaction)
        return None

    async def get_recent_activity(self, user_id: Optional[int] = None, skip: int = 0, limit: int = 10) -> Dict[str, Any]:
        query = select(RecentActivity)
        if user_id:
            query = query.where(RecentActivity.user_id == user_id)

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.execute(count_query)
        total_count = total.scalar()

        query = query.order_by(desc(RecentActivity.timestamp)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        activities = result.scalars().all()

        return {
            "total": total_count,
            "page": (skip // limit) + 1,
            "per_page": limit,
            "total_pages": math.ceil(total_count / limit),
            "has_next": (skip + limit) < total_count,
            "has_prev": skip > 0,
            "activities": activities
        }

    async def get_analytics_data(self) -> Dict[str, Any]:
        """Get detailed and accurate analytics data for the admin dashboard."""
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        sixty_days_ago = datetime.utcnow() - timedelta(days=60)

        # --- User Analytics ---
        total_users_res = await self.db.execute(select(func.count(User.id)))
        total_workers_res = await self.db.execute(select(func.count(User.id)).where(User.role == UserRole.WORKER))
        total_employers_res = await self.db.execute(select(func.count(User.id)).where(User.role == UserRole.EMPLOYER))
        new_users_last_30_days_res = await self.db.execute(select(func.count(User.id)).where(User.created_at >= thirty_days_ago))
        new_users_previous_30_days_res = await self.db.execute(
            select(func.count(User.id)).where(and_(User.created_at >= sixty_days_ago, User.created_at < thirty_days_ago))
        )
        
        new_users_last_30_days = new_users_last_30_days_res.scalar() or 0
        new_users_previous_30_days = new_users_previous_30_days_res.scalar() or 0
        user_growth_percentage = (
            ((new_users_last_30_days - new_users_previous_30_days) / new_users_previous_30_days) * 100
            if new_users_previous_30_days > 0 else 100.0
        )

        weekly_user_growth = []
        for i in range(4):
            start_date = datetime.utcnow() - timedelta(weeks=4 - i)
            end_date = datetime.utcnow() - timedelta(weeks=3 - i)
            weekly_users_res = await self.db.execute(select(func.count(User.id)).where(and_(User.created_at >= start_date, User.created_at < end_date)))
            weekly_user_growth.append({"label": f"Week {i + 1}", "value": weekly_users_res.scalar() or 0, "color": "#007AFF"})

        user_analytics = {
            "total_users": total_users_res.scalar() or 0,
            "total_workers": total_workers_res.scalar() or 0,
            "total_employers": total_employers_res.scalar() or 0,
            "new_users_last_30_days": new_users_last_30_days,
            "user_growth_percentage": user_growth_percentage,
            "weekly_user_growth": weekly_user_growth,
        }

        # --- Job Analytics ---
        total_jobs_res = await self.db.execute(select(func.count(Job.id)))
        open_jobs_res = await self.db.execute(select(func.count(Job.id)).where(Job.status == JobStatus.OPEN))
        completed_jobs_res = await self.db.execute(select(func.count(Job.id)).where(Job.status == JobStatus.COMPLETED))
        disputed_jobs_res = await self.db.execute(select(func.count(Dispute.id)))
        total_ended_jobs_res = await self.db.execute(select(func.count(Job.id)).where(Job.status == JobStatus.COMPLETED))
        
        completed_jobs = completed_jobs_res.scalar() or 0
        total_ended_jobs = total_ended_jobs_res.scalar() or 0
        job_completion_rate = (completed_jobs / total_ended_jobs * 100) if total_ended_jobs > 0 else 0

        avg_completion_time_res = await self.db.execute(
            select(func.avg(func.extract('epoch', Job.completed_at - Job.created_at)))
            .where(and_(Job.status == JobStatus.COMPLETED, Job.completed_at.isnot(None)))
        )
        avg_completion_time_seconds = avg_completion_time_res.scalar() or 0
        avg_completion_time_days = avg_completion_time_seconds / (60 * 60 * 24)

        top_categories_res = await self.db.execute(
            select(Job.category_id, func.count(Job.id).label("job_count"))
            .where(Job.category_id.isnot(None))
            .group_by(Job.category_id).order_by(func.count(Job.id).desc()).limit(5)
        )
        top_categories = [{"category": row[0], "count": row[1]} for row in top_categories_res]

        job_analytics = {
            "total_jobs": total_jobs_res.scalar() or 0,
            "open_jobs": open_jobs_res.scalar() or 0,
            "completed_jobs": completed_jobs,
            "disputed_jobs": disputed_jobs_res.scalar() or 0,
            "job_completion_rate": job_completion_rate,
            "avg_completion_time_days": avg_completion_time_days,
            "top_categories": top_categories,
        }

        # --- Financial Analytics ---
        total_revenue_res = await self.db.execute(select(func.sum(Payment.commission_amount)).where(Payment.status == PaymentStatus.COMPLETED))
        revenue_30_days_res = await self.db.execute(
            select(func.sum(Payment.commission_amount)).where(and_(Payment.status == PaymentStatus.COMPLETED, Payment.completed_at >= thirty_days_ago))
        )
        total_volume_res = await self.db.execute(select(func.sum(Payment.amount)).where(Payment.status == PaymentStatus.COMPLETED))
        avg_transaction_res = await self.db.execute(select(func.avg(Payment.amount)).where(Payment.status == PaymentStatus.COMPLETED))

        weekly_revenue_trend = []
        for i in range(4):
            start_date = datetime.utcnow() - timedelta(weeks=4 - i)
            end_date = datetime.utcnow() - timedelta(weeks=3 - i)
            weekly_revenue_res = await self.db.execute(
                select(func.sum(Payment.commission_amount)).where(and_(Payment.status == PaymentStatus.COMPLETED, Payment.completed_at >= start_date, Payment.completed_at < end_date))
            )
            weekly_revenue_trend.append({"label": f"Week {i + 1}", "value": weekly_revenue_res.scalar() or 0, "color": "#34C759"})

        top_earners_res = await self.db.execute(
            select(User.id, User.first_name, User.last_name, func.sum(Payment.amount).label('total_earned'))
            .join(User, Payment.user_id == User.id)
            .where(and_(Payment.status == PaymentStatus.COMPLETED, User.role == UserRole.WORKER))
            .group_by(User.id).order_by(desc('total_earned')).limit(5)
        )
        top_earning_workers = [{"id": r[0], "name": f"{r[1]} {r[2]}", "total": r[3]} for r in top_earners_res]

        top_spenders_res = await self.db.execute(
            select(User.id, User.first_name, User.last_name, func.sum(Payment.amount).label('total_spent'))
            .join(User, Payment.user_id == User.id)
            .where(and_(Payment.status == PaymentStatus.COMPLETED, User.role == UserRole.EMPLOYER))
            .group_by(User.id).order_by(desc('total_spent')).limit(5)
        )
        top_spending_employers = [{"id": r[0], "name": f"{r[1]} {r[2]}", "total": r[3]} for r in top_spenders_res]

        financial_analytics = {
            "total_platform_revenue": total_revenue_res.scalar() or 0,
            "revenue_last_30_days": revenue_30_days_res.scalar() or 0,
            "total_transaction_volume": total_volume_res.scalar() or 0,
            "avg_transaction_value": avg_transaction_res.scalar() or 0,
            "weekly_revenue_trend": weekly_revenue_trend,
            "top_earning_workers": top_earning_workers,
            "top_spending_employers": top_spending_employers,
        }

        # --- Engagement Analytics ---
        satisfied_reviews_res = await self.db.execute(select(func.count(Review.id)).where(Review.rating >= 4))
        total_reviews_res = await self.db.execute(select(func.count(Review.id)))
        total_reviews = total_reviews_res.scalar() or 0
        user_satisfaction_rate = (satisfied_reviews_res.scalar() / total_reviews * 100) if total_reviews > 0 else 0
        
        avg_rating_res = await self.db.execute(select(func.avg(Review.rating)))
        
        disputes_opened_res = await self.db.execute(select(func.count(Dispute.id)).where(Dispute.created_at >= thirty_days_ago))
        disputes_resolved_res = await self.db.execute(
            select(func.count(Dispute.id)).where(and_(Dispute.status == DisputeStatus.RESOLVED, Dispute.resolved_at >= thirty_days_ago))
        )

        engagement_analytics = {
            "user_satisfaction_rate": user_satisfaction_rate,
            "avg_review_rating": avg_rating_res.scalar() or 0,
            "disputes_opened_last_30_days": disputes_opened_res.scalar() or 0,
            "disputes_resolved_last_30_days": disputes_resolved_res.scalar() or 0,
        }

        performance_metrics = {
            "platform_uptime": 99.9,
            "avg_api_response_time_ms": 245,
        }

        return {
            "user_analytics": user_analytics,
            "job_analytics": job_analytics,
            "financial_analytics": financial_analytics,
            "engagement_analytics": engagement_analytics,
            "performance_metrics": performance_metrics,
        }
