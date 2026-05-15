from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from sqlalchemy.orm import joinedload, selectinload
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from enum import Enum
import asyncio
import random

from app.models.user import User
from app.models.job import Job, JobStatus
from app.models.job_application import JobApplication, ApplicationStatus
from app.schemas.job_application import JobApplicationInDB
from app.models.payment import Payment, PaymentStatus
from app.models.recent_activity import RecentActivity
from app.models.notification import Notification
from app.models.review import Review
from app.models.profile_view import ProfileView
from app.models.worker_profile import RecentWork
from app.services.location_service import LocationService
from app.schemas.worker_profile import ServiceShowcaseItem, ServiceShowcaseWorker
from app.schemas.employer_dashboard import (
    DashboardMetricsSchema,
    EnrichedRecentActivitySchema,
    ActiveJobSchema,
    PaymentSummarySchema,
    PaymentHistorySchema,
    JobApplicationDetailSchema,
    EmployerDashboardSchema,
    UnreadNotificationCountSchema,
    ActivityType,
    EmployerWalletSchema
)


class EmployerDashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_metrics(self, user_id: int) -> DashboardMetricsSchema:
        """Get comprehensive dashboard metrics for employer"""
        
        # Get active jobs count
        active_jobs_stmt = select(func.count(Job.id)).where(
            and_(
                Job.employer_id == user_id,
                Job.status.in_([JobStatus.OPEN, JobStatus.IN_PROGRESS])
            )
        )
        active_jobs_result = await self.db.execute(active_jobs_stmt)
        active_jobs = active_jobs_result.scalar() or 0

        # Get total jobs
        total_jobs_stmt = select(func.count(Job.id)).where(Job.employer_id == user_id)
        total_jobs_result = await self.db.execute(total_jobs_stmt)
        total_jobs = total_jobs_result.scalar() or 0

        # Get new applications (last 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        new_apps_stmt = select(func.count(JobApplication.id)).where(
            and_(
                JobApplication.job_id.in_(
                    select(Job.id).where(Job.employer_id == user_id)
                ),
                JobApplication.created_at >= thirty_days_ago,
                JobApplication.status == ApplicationStatus.PENDING
            )
        )
        new_apps_result = await self.db.execute(new_apps_stmt)
        new_applications = new_apps_result.scalar() or 0

        # Get total applications
        total_apps_stmt = select(func.count(JobApplication.id)).where(
            JobApplication.job_id.in_(
                select(Job.id).where(Job.employer_id == user_id)
            )
        )
        total_apps_result = await self.db.execute(total_apps_stmt)
        total_applications = total_apps_result.scalar() or 0

        # Get payment information
        user = await self.db.get(User, user_id)
        wallet_balance = user.wallet_balance if user else 0.0

        # Get pending payments
        pending_payments_stmt = select(func.sum(Payment.amount)).where(
            and_(
                Payment.user_id == user_id,
                Payment.status == PaymentStatus.PENDING
            )
        )
        pending_payments_result = await self.db.execute(pending_payments_stmt)
        pending_payments = pending_payments_result.scalar() or 0.0

        # Get total earnings
        total_earnings_stmt = select(func.sum(Payment.amount)).where(
            and_(
                Payment.user_id == user_id,
                Payment.status == PaymentStatus.COMPLETED
            )
        )
        total_earnings_result = await self.db.execute(total_earnings_stmt)
        total_earnings = total_earnings_result.scalar() or 0.0

        # Get profile views this month
        profile_views_this_month_stmt = select(func.count(ProfileView.id)).where(
            and_(
                ProfileView.user_id == user_id,
                ProfileView.viewed_at >= thirty_days_ago
            )
        )
        profile_views_this_month_result = await self.db.execute(profile_views_this_month_stmt)
        profile_views_this_month = profile_views_this_month_result.scalar() or 0

        # Get total profile views
        total_profile_views_stmt = select(func.count(ProfileView.id)).where(
            ProfileView.user_id == user_id
        )
        total_profile_views_result = await self.db.execute(total_profile_views_stmt)
        profile_views_total = total_profile_views_result.scalar() or 0

        # Get average rating
        avg_rating_stmt = select(func.avg(Review.rating)).where(
            Review.reviewee_id == user_id
        )
        avg_rating_result = await self.db.execute(avg_rating_stmt)
        average_rating = float(avg_rating_result.scalar() or 0.0)

        # Get total reviews
        total_reviews_stmt = select(func.count(Review.id)).where(
            Review.reviewee_id == user_id
        )
        total_reviews_result = await self.db.execute(total_reviews_stmt)
        total_reviews = total_reviews_result.scalar() or 0

        # Calculate response rate (applications responded to / total applications)
        responded_apps_stmt = select(func.count(JobApplication.id)).where(
            and_(
                JobApplication.job_id.in_(
                    select(Job.id).where(Job.employer_id == user_id)
                ),
                JobApplication.status.in_([
                    ApplicationStatus.ACCEPTED,
                    ApplicationStatus.REJECTED
                ])
            )
        )
        responded_apps_result = await self.db.execute(responded_apps_stmt)
        responded_applications = responded_apps_result.scalar() or 0
        response_rate = (responded_applications / total_applications * 100) if total_applications > 0 else 0.0

        # Calculate completion rate
        completed_jobs_stmt = select(func.count(Job.id)).where(
            and_(
                Job.employer_id == user_id,
                Job.status == JobStatus.COMPLETED
            )
        )
        completed_jobs_result = await self.db.execute(completed_jobs_stmt)
        completed_jobs = completed_jobs_result.scalar() or 0
        completion_rate = (completed_jobs / total_jobs * 100) if total_jobs > 0 else 0.0

        return DashboardMetricsSchema(
            active_jobs=active_jobs,
            total_jobs=total_jobs,
            new_applications=new_applications,
            total_applications=total_applications,
            pending_payments=pending_payments,
            total_earnings=total_earnings,
            wallet_balance=wallet_balance,
            profile_views_this_month=profile_views_this_month,
            profile_views_total=profile_views_total,
            average_rating=average_rating,
            total_reviews=total_reviews,
            response_rate=response_rate,
            completion_rate=completion_rate,
            completed_jobs=completed_jobs,
            active_jobs_trend=await self._calculate_trend(
                self._get_active_jobs_count_for_period, user_id
            ),
            new_applications_trend=await self._calculate_trend(
                self._get_new_applications_count_for_period, user_id
            ),
            profile_views_trend=await self._calculate_trend(
                self._get_profile_views_count_for_period, user_id
            ),
            wallet_balance_trend=await self._calculate_trend(
                self._get_wallet_balance_for_period, user_id
            ),
            job_views_trend=await self._calculate_trend(
                self._get_job_views_count_for_period, user_id
            ),
            completed_jobs_trend=await self._calculate_trend(
                self._get_completed_jobs_count_for_period, user_id
            ),
        )

    async def _calculate_trend(self, fetch_func, user_id: int) -> Dict[str, Any]:
        """Helper to calculate trend data for a given metric"""
        
        # Current week
        today = datetime.utcnow()
        start_of_current_week = today - timedelta(days=today.weekday())
        end_of_current_week = start_of_current_week + timedelta(days=6)
        
        # Previous week
        start_of_previous_week = start_of_current_week - timedelta(days=7)
        end_of_previous_week = start_of_current_week - timedelta(days=1)
        
        current_week_count = await fetch_func(user_id, start_of_current_week, end_of_current_week)
        previous_week_count = await fetch_func(user_id, start_of_previous_week, end_of_previous_week)

        current_val = float(current_week_count or 0)
        previous_val = float(previous_week_count or 0)

        if previous_val > 0:
            percentage_change = ((current_val - previous_val) / previous_val) * 100
        elif current_val > 0:
            percentage_change = 100.0
        else:
            percentage_change = 0.0
            
        return {
            "positive": percentage_change >= 0,
            "text": f"{percentage_change:+.0f}% this week"
        }

    async def _get_active_jobs_count_for_period(self, user_id: int, start_date: datetime, end_date: datetime) -> int:
        """Get active jobs count for a specific period"""
        stmt = select(func.count(Job.id)).where(
            and_(
                Job.employer_id == user_id,
                Job.status.in_([JobStatus.OPEN, JobStatus.IN_PROGRESS]),
                Job.created_at.between(start_date, end_date)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _get_new_applications_count_for_period(self, user_id: int, start_date: datetime, end_date: datetime) -> int:
        """Get new applications count for a specific period"""
        stmt = select(func.count(JobApplication.id)).where(
            and_(
                JobApplication.job_id.in_(
                    select(Job.id).where(Job.employer_id == user_id)
                ),
                JobApplication.created_at.between(start_date, end_date)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _get_profile_views_count_for_period(self, user_id: int, start_date: datetime, end_date: datetime) -> int:
        """Get profile views count for a specific period"""
        stmt = select(func.count(ProfileView.id)).where(
            and_(
                ProfileView.user_id == user_id,
                ProfileView.viewed_at.between(start_date, end_date)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _get_wallet_balance_for_period(self, user_id: int, start_date: datetime, end_date: datetime) -> float:
        """Get wallet balance for a specific period"""
        stmt = select(func.sum(Payment.amount)).where(
            and_(
                Payment.user_id == user_id,
                Payment.created_at.between(start_date, end_date)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0.0

    async def _get_job_views_count_for_period(self, user_id: int, start_date: datetime, end_date: datetime) -> int:
        """Get job views count for a specific period"""
        stmt = select(func.count(ProfileView.id)).where(
            and_(
                ProfileView.target_type == 'job',
                ProfileView.target_id.in_(
                    select(Job.id).where(Job.employer_id == user_id)
                ),
                ProfileView.viewed_at.between(start_date, end_date)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _get_completed_jobs_count_for_period(self, user_id: int, start_date: datetime, end_date: datetime) -> int:
        """Get completed jobs count for a specific period"""
        stmt = select(func.count(Job.id)).where(
            and_(
                Job.employer_id == user_id,
                Job.status == JobStatus.COMPLETED,
                Job.updated_at.between(start_date, end_date)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def get_enriched_recent_activities(
        self,
        user_id: int,
        limit: int = 10
    ) -> List[EnrichedRecentActivitySchema]:
        """Get recent activities with enriched data"""
        
        job_related_activities = [
            "job_application",
            "job_completion",
            "job_posted",
            "worker_hired",
            "job_cancelled",
        ]
        
        stmt = select(RecentActivity).where(
            and_(
                RecentActivity.user_id == user_id,
                RecentActivity.activity_type.in_(job_related_activities)
            )
        ).order_by(desc(RecentActivity.timestamp)).limit(limit)
        
        result = await self.db.execute(stmt)
        activities = result.scalars().all()
        
        enriched_activities = []
        for activity in activities:
            enriched = await self._enrich_activity(activity)
            enriched_activities.append(enriched)
        
        return enriched_activities

    async def _enrich_activity(self, activity: RecentActivity) -> EnrichedRecentActivitySchema:
        """Enrich activity with additional context"""
        
        activity_type = ActivityType(activity.activity_type)
        time_ago = self._get_time_ago_string(activity.timestamp)
        
        title = "New Activity"
        subtitle = activity.description
        
        # Extract metadata based on activity type
        target_id = activity.activity_data.get("target_id") if activity.activity_data else None
        target_name = activity.activity_data.get("target_name") if activity.activity_data else None
        target_image_url = activity.activity_data.get("target_image_url") if activity.activity_data else None
        action_label = activity.activity_data.get("action_label", "View") if activity.activity_data else "View"
        
        description = activity.description
        
        if activity.activity_type == "profile_view":
            title = "Profile View"
            viewer_id = activity.activity_data.get("viewer_id")
            if viewer_id:
                viewer = await self.db.get(User, viewer_id)
                if viewer:
                    subtitle = f"{viewer.first_name} {viewer.last_name} viewed your profile."
                    description = f"Your profile was viewed by {viewer.first_name} {viewer.last_name}."

        elif activity.activity_type == "job_application":
            title = "New Job Application"
            applicant_id = activity.activity_data.get("applicant_id")
            job_id = activity.activity_data.get("job_id")
            if applicant_id and job_id:
                applicant = await self.db.get(User, applicant_id)
                job = await self.db.get(Job, job_id)
                if applicant and job:
                    subtitle = f"{applicant.first_name} {applicant.last_name} applied to '{job.title}'."
                    description = f"A new application was submitted for your job posting: '{job.title}'."

        elif activity.activity_type == "job_completion":
            title = "Job Completed"
            worker_id = activity.activity_data.get("worker_id")
            job_id = activity.activity_data.get("job_id")
            if worker_id and job_id:
                worker = await self.db.get(User, worker_id)
                job = await self.db.get(Job, job_id)
                if worker and job:
                    subtitle = f"'{job.title}' was completed by {worker.first_name}."
                    description = f"The job '{job.title}' has been marked as completed by {worker.first_name} {worker.last_name}."

        elif activity.activity_type == "payment_request":
            title = "Payment Request"
            worker_id = activity.activity_data.get("worker_id")
            job_id = activity.activity_data.get("job_id")
            amount = activity.activity_data.get("amount")
            if worker_id and job_id and amount:
                worker = await self.db.get(User, worker_id)
                job = await self.db.get(Job, job_id)
                if worker and job:
                    subtitle = f"{worker.first_name} requests ₦{amount} for '{job.title}'."
                    description = f"A payment of ₦{amount} has been requested by {worker.first_name} {worker.last_name} for the completed job: '{job.title}'."
        
        elif activity.activity_type == "payment_sent":
            title = "Payment Sent"
            worker_id = activity.activity_data.get("worker_id")
            job_id = activity.activity_data.get("job_id")
            amount = activity.activity_data.get("amount")
            if worker_id and job_id and amount:
                worker = await self.db.get(User, worker_id)
                job = await self.db.get(Job, job_id)
                if worker and job:
                    subtitle = f"You paid {worker.first_name} ₦{amount} for '{job.title}'."
                    description = f"You have successfully sent a payment of ₦{amount} to {worker.first_name} {worker.last_name} for the job: '{job.title}'."

        elif activity.activity_type == "wallet_funded":
            title = "Wallet Funded"
            amount = activity.activity_data.get("amount")
            if amount:
                subtitle = f"You funded your wallet with ₦{amount}."
                description = f"Your wallet has been successfully funded with ₦{amount}."
        
        elif activity.activity_type == "withdrawal_request":
            title = "Withdrawal Request"
            amount = activity.activity_data.get("amount")
            if amount:
                subtitle = f"You requested a withdrawal of ₦{amount}."
                description = f"Your withdrawal request of ₦{amount} is being processed."
        
        elif activity.activity_type == "withdrawal_completed":
            title = "Withdrawal Completed"
            amount = activity.activity_data.get("amount")
            if amount:
                subtitle = f"Your withdrawal of ₦{amount} was successful."
                description = f"The withdrawal of ₦{amount} has been successfully processed and sent to your bank account."
        
        elif activity.activity_type == "withdrawal_failed":
            title = "Withdrawal Failed"
            amount = activity.activity_data.get("amount")
            if amount:
                subtitle = f"Your withdrawal of ₦{amount} failed."
                description = f"We were unable to process your withdrawal of ₦{amount}. Please contact support for assistance."

        return EnrichedRecentActivitySchema(
            id=activity.id,
            user_id=activity.user_id,
            activity_type=activity_type,
            title=title,
            subtitle=subtitle,
            description=description,
            action_label=action_label,
            target_id=target_id,
            target_name=target_name,
            target_image_url=target_image_url,
            metadata=activity.activity_data,
            timestamp=activity.timestamp,
            time_ago=time_ago
        )

    async def get_recent_activity(self, user_id: int, limit: int = 20) -> List[EnrichedRecentActivitySchema]:
        """Get a detailed list of recent activities"""
        
        stmt = select(RecentActivity).where(
            RecentActivity.user_id == user_id
        ).order_by(desc(RecentActivity.timestamp)).limit(limit)
        
        result = await self.db.execute(stmt)
        activities = result.scalars().all()
        
        enriched_activities = []
        for activity in activities:
            enriched = await self._enrich_activity(activity)
            enriched_activities.append(enriched)
            
        return enriched_activities

    async def get_active_jobs(self, user_id: int, limit: int = 5) -> List[ActiveJobSchema]:
        """Get all jobs for employer with analytics (not limited to active status)"""
        
        stmt = select(Job).where(
            Job.employer_id == user_id
        ).order_by(desc(Job.created_at)).limit(limit)
        
        result = await self.db.execute(stmt)
        jobs = result.scalars().all()
        
        active_jobs_list = []
        for job in jobs:
            # Get applications count
            apps_stmt = select(func.count(JobApplication.id)).where(
                JobApplication.job_id == job.id
            )
            apps_result = await self.db.execute(apps_stmt)
            applications_count = apps_result.scalar() or 0
            
            # Get views count
            views_stmt = select(func.count(ProfileView.id)).where(
                and_(
                    ProfileView.target_type == 'job',
                    ProfileView.target_id == job.id
                )
            )
            views_result = await self.db.execute(views_stmt)
            views_count = views_result.scalar() or 0
            
            job_analytics = {
                "total_applicants": applications_count,
                "total_views": views_count,
                "posted_at": job.created_at
            }
            
            active_jobs_list.append(ActiveJobSchema(
                job_id=job.id,
                title=job.title,
                status=job.status.value,
                created_at=job.created_at,
                location=job.location,
                city=job.city,
                country=job.country,
                location_type=job.location_type.value,
                job_price=job.job_price,
                hourly_rate=job.hourly_rate,
                estimated_hours=job.estimated_hours,
                analytics=job_analytics
            ))
            
        return active_jobs_list

    async def get_payment_summary(self, user_id: int) -> PaymentSummarySchema:
        """Get payment summary"""
        
        user = await self.db.get(User, user_id)
        
        # Get pending payments
        pending_stmt = select(func.sum(Payment.amount)).where(
            and_(
                Payment.user_id == user_id,
                Payment.status == PaymentStatus.PENDING
            )
        )
        pending_result = await self.db.execute(pending_stmt)
        pending_payments = pending_result.scalar() or 0.0

        # Get released payments
        released_stmt = select(func.sum(Payment.amount)).where(
            and_(
                Payment.user_id == user_id,
                Payment.status == PaymentStatus.COMPLETED
            )
        )
        released_result = await self.db.execute(released_stmt)
        released_payments = released_result.scalar() or 0.0
        
        # Get total earnings (released + pending)
        total_earnings = pending_payments + released_payments

        # Get transaction count
        count_stmt = select(func.count(Payment.id)).where(
            Payment.user_id == user_id
        )
        count_result = await self.db.execute(count_stmt)
        total_transactions = count_result.scalar() or 0

        # Get this month earnings
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        this_month_stmt = select(func.sum(Payment.amount)).where(
            and_(
                Payment.user_id == user_id,
                Payment.created_at >= thirty_days_ago,
                Payment.status == PaymentStatus.COMPLETED
            )
        )
        this_month_result = await self.db.execute(this_month_stmt)
        this_month_earnings = this_month_result.scalar() or 0.0

        # Get last transaction date
        last_trans_stmt = select(Payment.created_at).where(
            Payment.user_id == user_id
        ).order_by(desc(Payment.created_at)).limit(1)
        last_trans_result = await self.db.execute(last_trans_stmt)
        last_transaction_date = last_trans_result.scalar()

        return PaymentSummarySchema(
            total_earnings=total_earnings,
            pending_payments=pending_payments,
            released_payments=released_payments,
            wallet_balance=user.wallet_balance if user else 0.0,
            total_transactions=total_transactions,
            this_month_earnings=this_month_earnings,
            last_transaction_date=last_transaction_date
        )

    async def get_payment_history(
        self, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 10
    ) -> List[PaymentHistorySchema]:
        """Get payment history"""
        
        stmt = select(Payment).where(
            Payment.user_id == user_id
        ).order_by(desc(Payment.created_at)).offset(skip).limit(limit)
        
        result = await self.db.execute(stmt)
        payments = result.scalars().all()
        
        history = []
        for payment in payments:
            job_title = None
            if payment.job_id:
                job = await self.db.get(Job, payment.job_id)
                job_title = job.title if job else "Unknown Job"
            
            worker_name = None
            if payment.job and payment.job.worker_id:
                worker = await self.db.get(User, payment.job.worker_id)
                worker_name = f"{worker.first_name} {worker.last_name}" if worker else "Unknown Worker"

            transaction_type = "unknown"
            description = "Transaction"

            if payment.amount > 0:
                transaction_type = "deposit"
                description = "Wallet Deposit"
            else:
                if payment.job_id:
                    transaction_type = "payment"
                    description = f"Paid for '{job_title}'"
                else:
                    transaction_type = "withdrawal"
                    description = "Withdrawal"
            
            history.append(PaymentHistorySchema(
                id=payment.id,
                job_id=payment.job_id,
                job_title=job_title,
                worker_id=payment.job.worker_id if payment.job else None,
                worker_name=worker_name,
                amount=payment.amount,
                status=payment.status.value,
                transaction_type=transaction_type,
                created_at=payment.created_at,
                description=description
            ))
        
        return history

    async def get_pending_applications(
        self, 
        user_id: int, 
        limit: int = 5
    ) -> List[JobApplicationDetailSchema]:
        """Get pending job applications"""
        
        stmt = select(JobApplication).join(Job).where(
            and_(
                Job.employer_id == user_id,
                JobApplication.status == ApplicationStatus.PENDING
            )
        ).order_by(desc(JobApplication.created_at)).limit(limit)
        
        result = await self.db.execute(stmt)
        applications = result.scalars().all()
        
        details = []
        for app in applications:
            worker = await self.db.get(User, app.worker_id)
            
            # Get worker's completed jobs
            completed_jobs_stmt = select(func.count(Job.id)).where(
                and_(
                    Job.worker_id == app.worker_id,
                    Job.status == JobStatus.COMPLETED
                )
            )
            completed_jobs_result = await self.db.execute(completed_jobs_stmt)
            completed_jobs = completed_jobs_result.scalar() or 0
            
            # Get worker's average rating
            avg_rating_stmt = select(func.avg(Review.rating)).where(
                Review.reviewee_id == app.worker_id
            )
            avg_rating_result = await self.db.execute(avg_rating_stmt)
            worker_rating = float(avg_rating_result.scalar() or 0.0)
            
            # Calculate response time
            response_time_hours = None
            if app.created_at:
                response_time_hours = int((datetime.now(timezone.utc) - app.created_at).total_seconds() / 3600)
            
            details.append(JobApplicationDetailSchema(
                id=app.id,
                job_id=app.job_id,
                worker_id=app.worker_id,
                worker_name=f"{worker.first_name} {worker.last_name}" if worker else "Unknown",
                worker_avatar=worker.avatar_url if worker else None,
                worker_rating=worker_rating,
                worker_completed_jobs=completed_jobs,
                proposal=app.proposal_text if hasattr(app, 'proposal_text') else None,
                status=app.status.value,
                applied_at=app.created_at,
                response_time_hours=response_time_hours
            ))
        
        return details

    async def get_nearby_workers(self, user_id: int, radius_km: Optional[int] = None, limit: int = 10) -> List:
        """Get nearby workers based on user location"""
        import logging
        logger = logging.getLogger(__name__)
        
        # Get user's location
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalars().first()
        if not user or user.latitude is None or user.longitude is None:
            logger.debug(f'[get_nearby_workers] User {user_id} has no location set, returning empty')
            return []
        
        radius_km = LocationService.resolve_search_radius_km(user=user, radius_km=radius_km)
        logger.info(f'[get_nearby_workers] Fetching workers within {radius_km}km of ({user.latitude}, {user.longitude})')
        
        location_service = LocationService(self.db)
        nearby_workers_tuples = await location_service.get_nearby_workers(
            employer_latitude=user.latitude,
            employer_longitude=user.longitude,
            radius_km=radius_km,
            min_rating=0.0,
            limit=limit
        )
        
        # Convert worker ORM objects to dicts for serialization
        workers_list = []
        for worker, distance in nearby_workers_tuples:
            worker_dict = {
                "id": worker.id,
                "first_name": worker.first_name,
                "last_name": worker.last_name,
                "headline": getattr(worker, 'headline', None),
                "avatar_url": worker.avatar_url,
                "reputation_score": float(worker.reputation_score or 0.0),
                "location": worker.location,
                "latitude": worker.latitude,
                "longitude": worker.longitude,
                "distance_km": round(distance, 2),
                "distance_display": LocationService.format_distance(distance)
            }
            workers_list.append(worker_dict)
        
        logger.info(f'[get_nearby_workers] Found {len(workers_list)} nearby workers')
        return workers_list[:limit]

    async def get_top_workers(self, user_id: int, radius_km: Optional[int] = None, limit: int = 10) -> List:
        """Get top-rated workers nearby sorted by reputation"""
        import logging
        logger = logging.getLogger(__name__)
        
        # Get user's location
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalars().first()
        if not user or user.latitude is None or user.longitude is None:
            logger.debug(f'[get_top_workers] User {user_id} has no location set, returning empty')
            return []
        
        radius_km = LocationService.resolve_search_radius_km(user=user, radius_km=radius_km)
        logger.info(f'[get_top_workers] Fetching top workers within {radius_km}km of ({user.latitude}, {user.longitude})')
        
        location_service = LocationService(self.db)
        top_workers_tuples = await location_service.get_nearby_workers(
            employer_latitude=user.latitude,
            employer_longitude=user.longitude,
            radius_km=radius_km,
            min_rating=0.0,
            limit=limit
        )
        
        # Extract workers from tuples and sort by reputation score descending (top workers by rating)
        workers = [worker for worker, distance in top_workers_tuples]
        sorted_workers = sorted(workers, key=lambda w: w.reputation_score, reverse=True)
        
        # Convert worker ORM objects to dicts for serialization
        workers_list = []
        for worker in sorted_workers:
            worker_dict = {
                "id": worker.id,
                "first_name": worker.first_name,
                "last_name": worker.last_name,
                "headline": getattr(worker, 'headline', None),
                "avatar_url": worker.avatar_url,
                "reputation_score": float(worker.reputation_score or 0.0),
                "location": worker.location,
                "latitude": worker.latitude,
                "longitude": worker.longitude
            }
            workers_list.append(worker_dict)
        
        logger.info(f'[get_top_workers] Found {len(workers_list)} top workers by reputation')
        return workers_list[:limit]

    async def get_nearby_services(self, user_id: int, radius_km: Optional[int] = None, limit: int = 10) -> List:
        """Get nearby services based on user location"""
        import logging
        from sqlalchemy import select
        from app.models.file import File
        
        logger = logging.getLogger(__name__)
        
        # Get user's location
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalars().first()
        if not user or user.latitude is None or user.longitude is None:
            logger.debug(f'[get_nearby_services] User {user_id} has no location set, returning empty')
            return []
        
        radius_km = LocationService.resolve_search_radius_km(user=user, radius_km=radius_km)
        logger.info(f'[get_nearby_services] Fetching services within {radius_km}km of ({user.latitude}, {user.longitude})')
        
        location_service = LocationService(self.db)
        nearby_services_tuples = await location_service.get_nearby_services(
            user_latitude=user.latitude,
            user_longitude=user.longitude,
            radius_km=radius_km,
            limit=limit
        )
        
        # Extract service objects and fetch their images
        result = []
        for service, distance in nearby_services_tuples:
            # Fetch images for this service
            images_result = await self.db.execute(
                select(File).where(
                    File.reference_id == service.id,
                    File.reference_type == "service"
                )
            )
            images = images_result.scalars().all()
            
            # Get first image as image_url
            image_url = images[0].file_path if images else None
            
            # Build service dict with all required fields
            # Make sure to convert numeric types for JSON serialization
            service_dict = {
                "id": service.id,
                "name": service.name,
                "description": service.description,
                "price": float(service.price) if service.price else 0.0,
                "image_url": image_url,
                "category_name": service.category.name if service.category else None,
                "city": service.city,
                "latitude": service.latitude,
                "longitude": service.longitude,
                "distance_km": round(distance, 2),
                "distance_display": LocationService.format_distance(distance),
                "worker": {
                    "id": service.worker.id,
                    "first_name": service.worker.first_name,
                    "last_name": service.worker.last_name,
                    "headline": service.worker.headline,
                    "avatar_url": service.worker.avatar_url,
                    "reputation_score": float(service.worker.reputation_score) if service.worker.reputation_score else 0.0,
                    "location": service.worker.location,
                    "latitude": service.worker.latitude,
                    "longitude": service.worker.longitude,
                } if service.worker else None
            }
            result.append(service_dict)
        
        logger.info(f'[get_nearby_services] Found {len(result)} nearby services')
        return result[:limit]

    async def get_complete_dashboard(self, user_id: int) -> EmployerDashboardSchema:
        """Get complete employer dashboard with all sections"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f'[get_complete_dashboard] Building dashboard for user {user_id}')
        
        stats = await self.get_dashboard_metrics(user_id)
        recent_activity = await self.get_enriched_recent_activities(user_id, limit=10)
        active_jobs = await self.get_active_jobs(user_id, limit=5)
        unread_notifications = await self.get_unread_notification_count(user_id)
        
        # Get user's preferred search radius
        user = await self.db.get(User, user_id)
        radius_km = LocationService.resolve_search_radius_km(user=user)
        
        # Fetch nearby/top workers and services in parallel
        nearby_workers = await self.get_nearby_workers(user_id, radius_km=radius_km, limit=10)
        top_workers = await self.get_top_workers(user_id, radius_km=radius_km, limit=10)
        nearby_services = await self.get_nearby_services(user_id, radius_km=radius_km, limit=10)
        
        logger.info(f'[get_complete_dashboard] Dashboard ready: {len(nearby_workers)} nearby workers, {len(top_workers)} top workers, {len(nearby_services)} nearby services')
        
        return EmployerDashboardSchema(
            stats=stats,
            recent_activity=recent_activity,
            active_jobs=active_jobs,
            unread_notifications=unread_notifications.unread_count,
            nearby_workers=nearby_workers,
            top_workers=top_workers,
            nearby_services=nearby_services
        )

    async def get_unread_notification_count(self, user_id: int) -> UnreadNotificationCountSchema:
        """Get unread notification count"""
        
        unread_stmt = select(func.count(Notification.id)).where(
            and_(
                Notification.user_id == user_id,
                Notification.read == False
            )
        )
        unread_result = await self.db.execute(unread_stmt)
        unread_count = unread_result.scalar() or 0

        total_stmt = select(func.count(Notification.id)).where(
            Notification.user_id == user_id
        )
        total_result = await self.db.execute(total_stmt)
        total_notifications = total_result.scalar() or 0

        return UnreadNotificationCountSchema(
            unread_count=unread_count,
            total_notifications=total_notifications
        )

    @staticmethod
    def _get_time_ago_string(timestamp: datetime) -> str:
        """Convert timestamp to 'X time ago' format"""
        now = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        diff = now - timestamp
        
        seconds = int(diff.total_seconds())
        minutes = seconds // 60
        hours = minutes // 60
        days = hours // 24
        
        if seconds < 60:
            return f"{seconds}s ago" if seconds > 1 else "just now"
        elif minutes < 60:
            return f"{minutes}m ago" if minutes > 1 else "1m ago"
        elif hours < 24:
            return f"{hours}h ago" if hours > 1 else "1h ago"
        elif days < 30:
            return f"{days}d ago" if days > 1 else "1d ago"
        else:
            months = days // 30
            return f"{months}mo ago" if months > 1 else "1mo ago"

    async def get_wallet_details(self, user_id: int) -> EmployerWalletSchema:
        """Get wallet details for employer"""
        
        user = await self.db.get(User, user_id)
        wallet_balance = user.wallet_balance if user else 0.0
        
        # Calculate total in (deposits)
        total_in_stmt = select(func.sum(Payment.amount)).where(
            and_(
                Payment.user_id == user_id,
                Payment.status == PaymentStatus.COMPLETED,
                Payment.amount > 0  # Assuming positive amounts are deposits
            )
        )
        total_in_result = await self.db.execute(total_in_stmt)
        total_in = total_in_result.scalar() or 0.0
        
        # Calculate total out (withdrawals/payments)
        total_out_stmt = select(func.sum(Payment.amount)).where(
            and_(
                Payment.user_id == user_id,
                Payment.status == PaymentStatus.COMPLETED,
                Payment.amount < 0  # Assuming negative amounts are withdrawals/payments
            )
        )
        total_out_result = await self.db.execute(total_out_stmt)
        total_out = total_out_result.scalar() or 0.0
        
        recent_transactions = await self.get_payment_history(user_id, limit=5)
        
        return EmployerWalletSchema(
            balance=wallet_balance,
            total_in=total_in,
            total_out=abs(total_out),
            recent_transactions=recent_transactions
        )

    async def get_recent_workers(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently paid workers"""
        
        stmt = select(Payment).where(
            and_(
                Payment.user_id == user_id,
                Payment.status == PaymentStatus.COMPLETED
            )
        ).order_by(desc(Payment.created_at)).limit(limit)
        
        result = await self.db.execute(stmt)
        payments = result.scalars().all()
        
        recent_workers = []
        worker_ids = set()
        
        for payment in payments:
            if payment.job and payment.job.worker_id and payment.job.worker_id not in worker_ids:
                worker = await self.db.get(User, payment.job.worker_id)
                if worker:
                    recent_workers.append({
                        "id": worker.id,
                        "first_name": worker.first_name,
                        "last_name": worker.last_name,
                        "avatar_url": worker.avatar_url
                    })
                    worker_ids.add(worker.id)
        
        return recent_workers

    async def get_all_applications(self, user_id: int, status: Optional[ApplicationStatus] = None) -> List[JobApplicationInDB]:
        """Get all job applications for the employer's jobs."""
        stmt = select(JobApplication).join(Job).where(
            Job.employer_id == user_id
        ).options(
            joinedload(JobApplication.worker),
            joinedload(JobApplication.job),
            selectinload(JobApplication.status_history)
        )
        if status:
            stmt = stmt.where(JobApplication.status == status)
        
        stmt = stmt.order_by(desc(JobApplication.created_at))

        result = await self.db.execute(stmt)
        applications = result.scalars().unique().all()
        
        return [JobApplicationInDB.from_orm(app) for app in applications]

    async def get_application_stats(self, user_id: int) -> Dict[str, int]:
        """Get application stats for the employer."""
        
        statuses = [ApplicationStatus.PENDING, ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED]
        
        tasks = [
            self.db.execute(
                select(func.count(JobApplication.id))
                .join(Job)
                .where(and_(Job.employer_id == user_id, JobApplication.status == status))
            ) for status in statuses
        ]
        
        results = await asyncio.gather(*tasks)
        
        total_stmt = select(func.count(JobApplication.id)).join(Job).where(Job.employer_id == user_id)
        total_result = await self.db.execute(total_stmt)
        
        return {
            "total": total_result.scalar() or 0,
            "pending": results[0].scalar() or 0,
            "accepted": results[1].scalar() or 0,
            "rejected": results[2].scalar() or 0,
        }


async def get_employer_dashboard(db: AsyncSession, user_id: int) -> EmployerDashboardSchema:
    service = EmployerDashboardService(db)
    
    stats = await service.get_dashboard_metrics(user_id)
    recent_activity = await service.get_enriched_recent_activities(user_id, limit=5)
    active_jobs = await service.get_active_jobs(user_id, limit=3)
    unread_notifications = await service.get_unread_notification_count(user_id)

    return EmployerDashboardSchema(
        stats=stats,
        recent_activity=recent_activity,
        active_jobs=active_jobs,
        unread_notifications=unread_notifications.unread_count,
    )

async def get_featured_services(
    db: AsyncSession, limit: int = 10, exclude_user_id: int = None
) -> List[ServiceShowcaseItem]:
    """
    Fetches a list of featured worker services to be showcased on employer home screen.
    Returns actual Service records from workers (not recent works).
    Optionally excludes services posted by a specific user (e.g., current user).
    """
    from app.models.service import Service
    from app.models.category import Category
    from app.models.file import File
    
    print(f"[DEBUG] get_featured_services called with limit={limit}, exclude_user_id={exclude_user_id}")
    
    # Fetch services with their worker details
    stmt = (
        select(Service)
        .options(
            joinedload(Service.worker),
            joinedload(Service.category)
        )
        .order_by(desc(Service.id))
        .limit(50)  # Fetch a pool to randomize from
    )
    
    # Exclude current user's services if exclude_user_id is provided
    if exclude_user_id is not None:
        stmt = stmt.where(Service.worker_id != exclude_user_id)
    
    result = await db.execute(stmt)
    services = result.unique().scalars().all()

    print(f"[DEBUG] Total services fetched: {len(services)}")
    
    if not services:
        print("[DEBUG] No services found, returning empty list")
        return []

    # Randomly select a subset of the fetched services
    selected_services = random.sample(services, min(len(services), limit))
    print(f"[DEBUG] Selected {len(selected_services)} services to return")

    # Fetch images for each service
    showcase_items = []
    for service in selected_services:
        if not service.worker:
            continue
        
        # Fetch service images
        images_result = await db.execute(
            select(File).filter(
                File.reference_id == service.id,
                File.reference_type == "service"
            ).order_by(File.id)
        )
        images = images_result.scalars().all()
        
        # Calculate total reviews for this worker
        total_reviews_result = await db.execute(
            select(func.count(Review.id)).where(
                Review.reviewee_id == service.worker.id
            )
        )
        total_reviews = total_reviews_result.scalar() or 0
        
        print(f"[DEBUG] Service '{service.name}': {len(images)} images, worker: {service.worker.first_name} {service.worker.last_name}")
        
        # Build showcase item with complete service and worker data
        showcase_item = ServiceShowcaseItem(
            id=service.id,
            name=service.name,
            description=service.description,
            price=float(service.price),
            pricing_model=service.pricing_model,
            estimated_delivery_time=service.estimated_delivery_time,
            revisions=service.revisions,
            tags=service.tags or [],
            category_id=service.category_id,
            category_name=service.category.name if service.category else None,
            image_url=images[0].file_path if images else None,
            images=[
                {
                    "id": img.id,
                    "file_path": img.file_path,
                    "updated_at": img.updated_at.isoformat() if hasattr(img, 'updated_at') and img.updated_at else None
                }
                for img in images
            ],
            worker=ServiceShowcaseWorker(
                id=service.worker.id,
                first_name=service.worker.first_name,
                last_name=service.worker.last_name,
                headline=service.worker.headline,
                avatar_url=service.worker.avatar_url,
                rating=float(service.worker.reputation_score) if service.worker.reputation_score else 0.0,
                total_reviews=int(total_reviews),
            )
        )
        showcase_items.append(showcase_item)
    
    print(f"[DEBUG] Returning {len(showcase_items)} showcase items")
    return showcase_items
