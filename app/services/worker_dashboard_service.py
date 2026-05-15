from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, and_, select, desc
from sqlalchemy.orm import selectinload
from app.models.user import User as UserModel
from app.models.job_application import JobApplication, ApplicationStatus
from app.models.job import Job, JobStatus
from app.models.transaction import Transaction, TransactionType
from app.schemas.worker_dashboard import WorkerDashboardSchema, WorkerHomeScreenSchema, WorkerStats, ApplicationWithAction, BoostActivitySchema
from app.services.job_service import JobService
from app.services.notification_service import NotificationService
from app.services.recent_activity_service import RecentActivityService
from app.schemas.recent_activity import RecentActivityOut
from typing import List

async def get_worker_stats(db: AsyncSession, user_id: int) -> WorkerStats:
    total_applications_query = select(func.count(JobApplication.id)).where(JobApplication.worker_id == user_id)
    total_applications_result = await db.execute(total_applications_query)
    total_applications = total_applications_result.scalar_one_or_none() or 0

    active_contracts_query = select(func.count(Job.id)).join(JobApplication).where(
        and_(
            JobApplication.worker_id == user_id,
            JobApplication.status == ApplicationStatus.ACCEPTED,
            Job.status == JobStatus.IN_PROGRESS
        )
    )
    active_contracts_result = await db.execute(active_contracts_query)
    active_contracts = active_contracts_result.scalar_one_or_none() or 0

    total_earnings_query = select(func.sum(Transaction.amount)).where(
        and_(
            Transaction.user_id == user_id,
            Transaction.amount > 0
        )
    )
    total_earnings_result = await db.execute(total_earnings_query)
    total_earnings = total_earnings_result.scalar_one_or_none() or 0.0

    completed_jobs_query = select(func.count(Job.id)).join(JobApplication).where(
        and_(
            JobApplication.worker_id == user_id,
            JobApplication.status == ApplicationStatus.ACCEPTED,
            Job.status == JobStatus.COMPLETED
        )
    )
    completed_jobs_result = await db.execute(completed_jobs_query)
    completed_jobs = completed_jobs_result.scalar_one_or_none() or 0

    return WorkerStats(
        total_applications=total_applications,
        active_contracts=active_contracts,
        total_earnings=total_earnings,
        completed_jobs=completed_jobs,
    )

async def get_applications_with_actions(db: AsyncSession, user_id: int) -> List[ApplicationWithAction]:
    query = (
        select(JobApplication)
        .where(JobApplication.worker_id == user_id)
        .options(selectinload(JobApplication.job))
        .order_by(JobApplication.boosted.desc(), JobApplication.created_at.desc())
        .limit(3)
    )
    result = await db.execute(query)
    applications = result.scalars().all()

    applications_with_actions = []
    for app in applications:
        job_status = app.job.status if app.job else "unknown"
        action_type = "none"
        action = "No action recommended at this time."
        priority = 0
        
        # Determine action based on application and job status combination
        if app.status == ApplicationStatus.PENDING:
            if not app.boosted:
                action = "Boost your application to stand out and increase your chances of being hired!"
                action_type = "boost"
                priority = 1
            else:
                action = "Your application has been boosted. Waiting for employer review..."
                action_type = "none"
                priority = 0
        
        elif app.status == ApplicationStatus.REVIEWING:
            action = "The employer has viewed your application! Send a follow-up message to show your interest."
            action_type = "follow_up"
            priority = 2
        
        elif app.status == ApplicationStatus.ACCEPTED:
            if job_status == "draft":
                action = "Congratulations! Your application was accepted. Job details coming soon..."
                action_type = "none"
                priority = 0
            elif job_status == "open":
                action = "Your application was accepted! Job is starting soon. Get ready to begin."
                action_type = "none"
                priority = 1
            elif job_status == "in_progress":
                # Check if job needs completion marking
                if not app.job.worker_completed:
                    action = "Job in progress. Mark as complete when you finish to proceed with payment."
                    action_type = "mark_complete"
                    priority = 2
                elif app.job.worker_completed and not app.job.employer_completed:
                    action = "You marked the job complete. Waiting for employer confirmation to release payment..."
                    action_type = "none"
                    priority = 1
                else:
                    action = "Both parties confirmed completion. Payment is being processed..."
                    action_type = "none"
                    priority = 0
            elif job_status == "completed":
                if not app.job.worker_completed:
                    action = "Job is marked complete. Mark it as done on your end to confirm and receive payment."
                    action_type = "mark_complete"
                    priority = 2
                elif app.job.worker_completed and not app.job.employer_completed:
                    action = "You confirmed completion. Payment is pending employer confirmation..."
                    action_type = "none"
                    priority = 1
                else:
                    # Both completed - check if review is pending
                    action = "Job completed successfully! Leave a review to help the employer improve their services."
                    action_type = "review"
                    priority = 1
        
        applications_with_actions.append(
            ApplicationWithAction(
                id=app.id,
                job_id=app.job.id,
                job_title=app.job.title,
                status=app.status,
                job_status=job_status,
                recommended_action=action,
                action_type=action_type,
                boosted=app.boosted,
                worker_completed=app.job.worker_completed if app.job else False,
                employer_completed=app.job.employer_completed if app.job else False,
                priority=priority
            )
        )
    
    # Sort by priority (high to low) first, then by boosted status
    applications_with_actions.sort(key=lambda x: (-x.priority, -int(x.boosted)))
    
    return applications_with_actions

async def get_boost_activities(db: AsyncSession, user_id: int) -> List[BoostActivitySchema]:
    query = (
        select(Transaction.id, Job.title.label("job_title"), Transaction.amount, Transaction.created_at)
        .join(Job, Transaction.job_id == Job.id)
        .where(
            and_(
                Transaction.user_id == user_id,
                Transaction.transaction_type == TransactionType.BOOST
            )
        )
        .order_by(desc(Transaction.created_at))
        .limit(5)
    )
    result = await db.execute(query)
    boost_activities_data = result.mappings().all()

    return [
        BoostActivitySchema(
            id=activity["id"],
            job_title=activity["job_title"],
            amount=activity["amount"],
            created_at=activity["created_at"],
        )
        for activity in boost_activities_data
    ]

async def get_worker_dashboard_data(db: AsyncSession, user: UserModel) -> WorkerHomeScreenSchema:
    stats = await get_worker_stats(db, user.id)

    job_service = JobService(db)
    notification_service = NotificationService(db)
    recent_activity_service = RecentActivityService(db)

    recommended_jobs = await job_service.get_recommended_jobs(user)

    applications = await job_service.get_worker_applications(user.id)

    recent_activity_models = await recent_activity_service.get_activities_for_user(user.id)
    recent_activity = [RecentActivityOut.from_orm(activity) for activity in recent_activity_models]

    unread_notifications = await notification_service.get_unread_notification_count(user.id)

    applications_with_actions = await get_applications_with_actions(db, user.id)

    boost_activities = await get_boost_activities(db, user.id)

    dashboard_data = WorkerDashboardSchema(
        stats=stats,
        recommended_jobs=recommended_jobs,
        applications=applications,
        recent_activity=recent_activity,
        unread_notifications=unread_notifications,
        applications_with_actions=applications_with_actions,
        boost_activities=boost_activities,
    )

    return WorkerHomeScreenSchema(
        user=user,
        dashboard=dashboard_data,
    )
