from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from typing import List, Dict, Any
from datetime import datetime, timezone
import logging

from ..models.user import User, UserRole
from ..services.auth_service import get_current_user, get_admin_user

logger = logging.getLogger(__name__)
from ..schemas.admin import (
    DashboardStats,
    UserList,
    AdminJobList,
    AdminJobInDB,
    DisputeList,
    ContentModerationList,
    ReviewList,
    BadgeList,
    WalletFundingRequest,
    PaystackWebhookData,
    RecentActivityList,
    AdminDisputeResolution,
    JobApplicantList,
    AdminUser,
    AnalyticsData,
    TransactionList,
    AdminTransaction,
)
from ..schemas.payment import PaymentResponse
from ..schemas.billing import SubscriptionResponse
from ..schemas.service import (
    ServiceCategoryCreate,
    ServiceCategoryUpdate,
    ServiceCategoryInDB,
    ServiceCreate,
    ServiceUpdate,
    ServiceInDB,
    ServiceCategoryWithServices,
)
from ..schemas.kyc import KYCVerification, KYCSubmission as KYCSubmissionSchema
from ..schemas.push_notification import (
    PushNotificationSend,
    PushNotificationSchedule,
    PushNotificationLogsListResponse,
    NotificationPreviewResponse,
    PushNotificationBroadcastResponse,
    PushNotificationLogResponse,
)
from ..services.admin_service import AdminService
from ..services.admin_push_service import AdminPushService
from ..services.kyc_service import KYCService
from ..database import get_db
from ..utils.security import check_permissions
from ..utils.email_service import EmailService
from ..config import settings
from . import revenue
from ..schemas.newsletter import Newsletter, NewsletterCreate, NewsletterUpdate
from ..services import newsletter_service
from ..services.referral_service import ReferralService
from ..schemas.referral import ReferralSettingsCreate, ReferralSettingsInDB
from ..schemas.category import CategoryInDB
from . import kyc

router = APIRouter(tags=["admin"])
router.include_router(revenue.router)

@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    stats = await admin_service.get_dashboard_stats()
    return stats

@router.get("/users", response_model=UserList)
async def list_users(
    role: UserRole = None,
    is_verified: bool = None,
    is_active: bool = None,
    kyc_status: str = None,
    q: str = None,
    location: str = None,
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    users = await admin_service.list_users(
        role, is_verified, is_active, kyc_status, q, location, skip, limit
    )
    return users


@router.get("/users/{user_id}", response_model=AdminUser)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    user = await admin_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

@router.get("/reviews", response_model=ReviewList)
async def list_reviews(
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    reviews = await admin_service.list_reviews(skip, limit)
    return reviews

@router.get("/badges", response_model=BadgeList)
async def list_badges(
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    badges = await admin_service.list_badges(skip, limit)
    return badges

@router.get("/jobs", response_model=AdminJobList)
async def list_jobs(
    status: str = None,
    has_dispute: bool = None,
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    jobs = await admin_service.list_jobs(status, has_dispute, skip, limit)
    return jobs


@router.get("/jobs/{job_id}", response_model=AdminJobInDB)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    job = await admin_service.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/applicants", response_model=JobApplicantList)
async def list_job_applicants(
    job_id: int,
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    applicants = await admin_service.list_job_applicants(job_id, skip, limit)
    return applicants

@router.get("/disputes", response_model=DisputeList)
async def list_disputes(
    status: str = None,
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    disputes = await admin_service.list_disputes(status, skip, limit)
    return disputes

@router.get("/recent-activity", response_model=RecentActivityList)
async def list_recent_activity(
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    activities = await admin_service.get_recent_activity(None, skip, limit)
    return activities


@router.get("/users/{user_id}/recent-activity", response_model=RecentActivityList)
async def get_user_recent_activity(
    user_id: int,
    skip: int = 0,
    limit: int = 5,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    activities = await admin_service.get_recent_activity(user_id, skip, limit)
    return activities


@router.get("/kyc/pending", response_model=UserList)
async def list_pending_kyc(
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    users = await admin_service.list_users(kyc_status="pending", skip=skip, limit=limit)
    return users

@router.get("/kyc/submissions", response_model=Dict[str, Any])
async def list_kyc_submissions(
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    submissions = await admin_service.list_kyc_submissions(skip=skip, limit=limit)
    return submissions

@router.get("/kyc/submissions/{submission_id}", response_model=KYCSubmissionSchema)
async def get_kyc_submission(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    kyc_service = KYCService(db)
    submission = await kyc_service.get_submission_by_id(submission_id)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    return submission

@router.post("/kyc/submissions/{submission_id}/verify", response_model=KYCSubmissionSchema)
async def verify_kyc_submission(
    submission_id: int,
    background_tasks: BackgroundTasks,
    verification: KYCVerification = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    kyc_service = KYCService(db)
    submission = await kyc_service.verify_submission(submission_id, verification)
    
    # Notify user of the verification outcome
    if submission and submission.user:
        status_text = "approved" if verification.is_approved else "rejected"
        email_service = EmailService()
        background_tasks.add_task(
            email_service.send_kyc_verification_update,
            to_email=submission.user.email,
            first_name=submission.user.first_name,
            status=status_text,
            status_label=status_text.title(),
            submission_date=datetime.now().strftime("%Y-%m-%d"),
            reviewed_date=datetime.now().strftime("%Y-%m-%d"),
            feedback=verification.notes,
            dashboard_url=f"{settings.API_BASE_URL}/dashboard"
        )
        
    return submission

@router.post("/disputes/{dispute_id}/resolve")
async def resolve_dispute(
    dispute_id: int,
    resolution_data: AdminDisputeResolution,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    dispute = await admin_service.resolve_dispute(dispute_id, resolution_data.resolution, current_user.id)
    
    # Notify involved parties
    if dispute:
        email_service = EmailService()
        for user in [dispute.employer, dispute.worker]:
            if user:
                background_tasks.add_task(
                    email_service.send_template_email,
                    to_email=user.email,
                    template_name='plain_wrapper.html',
                    subject=f"Dispute Resolution: Job #{dispute.job_id}",
                    context={
                        'title': f"Dispute Resolution: Job #{dispute.job_id}",
                        'message': f"The dispute has been resolved.\n\nResolution: {resolution_data.resolution}"
                    }
                )
    
    return {"status": "resolved"}

@router.get("/content-moderation", response_model=ContentModerationList)
async def list_flagged_content(
    content_type: str = None,
    status: str = None,
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    content = await admin_service.list_flagged_content(
        content_type, status, skip, limit
    )
    return content

@router.post("/content-moderation/{content_id}/moderate")
async def moderate_content(
    content_id: int,
    action: str,
    reason: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    result = await admin_service.moderate_content(content_id, action, reason)
    
    # Notify content owner
    if result and result.user:
        email_service = EmailService()
        background_tasks.add_task(
            email_service.send_template_email,
            to_email=result.user.email,
            template_name='plain_wrapper.html',
            subject="Content Moderation Notice",
            context={
                'title': "Content Moderation Notice",
                'message': f"Your content has been {action}.\n\nReason: {reason}"
            }
        )
    
    return {"status": "moderated"}

from ..schemas.admin import UserAction

@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: int,
    action: UserAction,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    user = await admin_service.suspend_user(user_id, action.reason, action.duration_days)
    
    if user:
        email_service = EmailService()
        background_tasks.add_task(
            email_service.send_template_email,
            to_email=user.email,
            template_name='plain_wrapper.html',
            subject="Account Suspended",
            context={
                'title': "Account Suspended",
                'message': f"Your account has been suspended for {action.duration_days} days.\n\nReason: {action.reason}"
            }
        )
    
    return {"status": "suspended"}


@router.get("/metrics")
async def get_platform_metrics(
    start_date: str,
    end_date: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    metrics = await admin_service.get_platform_metrics(start_date, end_date)
    return metrics

# Service Category Endpoints
@router.post("/service-categories", response_model=ServiceCategoryInDB)
async def create_service_category(
    category_data: ServiceCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    return await admin_service.create_service_category(category_data)

@router.get("/service-categories", response_model=List[ServiceCategoryInDB])
async def get_service_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    return await admin_service.get_service_categories()

@router.put("/service-categories/{category_id}", response_model=ServiceCategoryInDB)
async def update_service_category(
    category_id: int,
    category_data: ServiceCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    category = await admin_service.update_service_category(category_id, category_data)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service category not found")
    return category

@router.delete("/service-categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    if not await admin_service.delete_service_category(category_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service category not found")

# Service Endpoints
@router.post("/services", response_model=ServiceInDB)
async def create_service(
    service_data: ServiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    return await admin_service.create_service(service_data)

@router.get("/services", response_model=List[ServiceInDB])
async def get_services(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    return await admin_service.get_services()

@router.put("/services/{service_id}", response_model=ServiceInDB)
async def update_service(
    service_id: int,
    service_data: ServiceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    service = await admin_service.update_service(service_id, service_data)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service

@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    if not await admin_service.delete_service(service_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")


@router.post("/notify-waitlist")
def notify_waitlist(background_tasks: BackgroundTasks, current_user: User = Depends(get_admin_user)):
    background_tasks.add_task(send_launch_notifications)
    return {"message": "Launch notifications are being sent in the background"}

@router.post("/newsletters", response_model=Newsletter)
async def create_newsletter(newsletter: NewsletterCreate, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    return await newsletter_service.create_newsletter(db=db, newsletter=newsletter)

@router.get("/newsletters", response_model=List[Newsletter])
async def get_newsletters(db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    return await newsletter_service.get_newsletters(db=db)

@router.get("/newsletters/{newsletter_id}", response_model=Newsletter)
async def get_newsletter(newsletter_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    return await newsletter_service.get_newsletter(db=db, newsletter_id=newsletter_id)

@router.put("/newsletters/{newsletter_id}", response_model=Newsletter)
async def update_newsletter(newsletter_id: int, newsletter: NewsletterUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    return await newsletter_service.update_newsletter(db=db, newsletter_id=newsletter_id, newsletter=newsletter)

@router.delete("/newsletters/{newsletter_id}")
async def delete_newsletter(newsletter_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    return await newsletter_service.delete_newsletter(db=db, newsletter_id=newsletter_id)

@router.post("/newsletters/{newsletter_id}/send")
def send_newsletter_task(newsletter_id: int, background_tasks: BackgroundTasks, current_user: User = Depends(get_admin_user)):
    background_tasks.add_task(send_newsletter, newsletter_id)
    return {"message": "Newsletter is being sent in the background"}


@router.post("/referral-settings", response_model=ReferralSettingsInDB)
def create_or_update_referral_settings(
    settings: ReferralSettingsCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    referral_service = ReferralService(db)
    return referral_service.create_or_update_referral_settings(settings)


@router.get("/referral-settings", response_model=List[ReferralSettingsInDB])
def get_referral_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    referral_service = ReferralService(db)
    return referral_service.get_referral_settings()


@router.get("/analytics", response_model=AnalyticsData)
async def get_analytics_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN)),
):
    admin_service = AdminService(db)
    try:
        analytics_data = await admin_service.get_analytics_data()
        return analytics_data
    except HTTPException:
        # Re-raise HTTPExceptions from deeper layers unchanged
        raise
    except Exception as exc:
        # Log the actual error for debugging
        logger.error(f"Error fetching analytics data: {str(exc)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch analytics data"
        )


@router.get("/transactions", response_model=TransactionList)
async def list_transactions(
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    transactions = await admin_service.list_transactions(skip, limit)
    return transactions


@router.get("/transactions/{transaction_id}", response_model=AdminTransaction)
async def get_transaction(
    transaction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    admin_service = AdminService(db)
    transaction = await admin_service.get_transaction_by_id(transaction_id)
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return transaction


# ============== PUSH NOTIFICATION ROUTES ==============

@router.post("/push-notifications/preview", response_model=NotificationPreviewResponse)
async def preview_notification_recipients(
    filters_data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Preview how many users will receive a push notification based on filters"""
    from ..schemas.push_notification import NotificationTargetFilters
    
    try:
        filters = NotificationTargetFilters(**filters_data)
        admin_push_service = AdminPushService(db)
        breakdown = await admin_push_service.get_target_user_count(filters)
        
        return NotificationPreviewResponse(
            total_users=breakdown['total'],
            breakdown=breakdown,
            estimated_delivery_time="Immediate"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/push-notifications/preview-recipients", response_model=NotificationPreviewResponse)
async def preview_notification_recipients_legacy(
    filters_data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Legacy mobile endpoint for previewing recipients"""
    from ..schemas.push_notification import NotificationTargetFilters

    try:
        filters = NotificationTargetFilters(**filters_data)
        admin_push_service = AdminPushService(db)
        breakdown = await admin_push_service.get_target_user_count(filters)

        return NotificationPreviewResponse(
            total_users=breakdown['total'],
            breakdown=breakdown,
            estimated_delivery_time="Immediate"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/push-notifications/send", response_model=PushNotificationBroadcastResponse)
async def send_push_notification(
    notification: PushNotificationSend,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN)),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Send push notification immediately to targeted users"""
    try:
        print(f"[ADMIN] Push notification send endpoint called")
        print(f"[ADMIN] Admin user: {current_user.id} ({current_user.email})")
        print(f"[ADMIN] Notification: title={notification.title}, message={notification.message}")
        print(f"[ADMIN] Filters: {notification.filters}")
        
        admin_push_service = AdminPushService(db)
        result, total_sent = await admin_push_service.send_push_notification(
            admin_id=current_user.id,
            push_notification=notification
        )
        
        print(f"[ADMIN] Send result: {result}")
        print(f"[ADMIN] Total sent: {total_sent}")
        
        if not result['success']:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result['message'])
        
        return PushNotificationBroadcastResponse(
            success=True,
            total_recipients=total_sent,
            message=result['message'],
            failed_recipients=result.get('failed', 0)
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ADMIN] Exception in send: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error sending notification: {str(e)}")


@router.post("/push-notifications/schedule", response_model=Dict[str, Any])
async def schedule_push_notification(
    notification: PushNotificationSchedule,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Schedule push notification for delivery at a specific time"""
    try:
        admin_push_service = AdminPushService(db)
        scheduled = await admin_push_service.schedule_push_notification(
            admin_id=current_user.id,
            push_notification=notification,
        )

        now = datetime.now(timezone.utc)
        if scheduled.scheduled_time <= now:
            await admin_push_service.send_scheduled_notification(scheduled)
            return {
                "success": scheduled.status.value == "sent",
                "message": "Notification sent immediately",
                "scheduled_time": notification.scheduled_time,
                "status": scheduled.status.value,
                "scheduled_id": scheduled.id,
            }

        return {
            "success": True,
            "message": "Notification scheduled successfully",
            "scheduled_time": notification.scheduled_time,
            "status": scheduled.status.value,
            "scheduled_id": scheduled.id,
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/push-notifications/logs", response_model=PushNotificationLogsListResponse)
async def get_push_logs(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get paginated list of push notification delivery logs"""
    try:
        print(f"[ADMIN] Fetching push notification logs for admin {current_user.id}")
        print(f"[ADMIN] Pagination: skip={skip}, limit={limit}")
        
        admin_push_service = AdminPushService(db)
        logs, total = await admin_push_service.get_delivery_logs(
            admin_id=current_user.id,
            skip=skip,
            limit=limit
        )
        
        print(f"[ADMIN] Found {len(logs)} logs out of total {total}")
        
        return PushNotificationLogsListResponse(
            total=total,
            page=skip // limit + 1,
            limit=limit,
            notifications=[PushNotificationLogResponse.model_validate(log) for log in logs]
        )
    except Exception as e:
        print(f"[ADMIN] Error fetching logs: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/push-notifications/{log_id}/resend", response_model=Dict[str, Any])
async def resend_failed_notification(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Resend a specific failed push notification"""
    try:
        admin_push_service = AdminPushService(db)
        result = await admin_push_service.resend_specific_notification(log_id)
        
        return {
            "success": result['success'],
            "message": result['message'],
            "resent": result.get('resent', 0)
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/push-notifications/test", response_model=Dict[str, Any])
async def test_push_notification(
    push_token: str = Body(None, embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Send a test push notification - can use provided token or user's registered token"""
    try:
        admin_push_service = AdminPushService(db)
        
        # Determine which token to use
        token_to_use = push_token
        
        # If no token provided, try to use user's registered token
        if not token_to_use:
            # Refresh the session to get fresh user data from database
            await db.refresh(current_user)
            
            # Also explicitly query the user to ensure we have the latest data
            stmt = select(User).where(User.id == current_user.id)
            result = await db.execute(stmt)
            user = result.scalar()
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Admin user not found"
                )
            
            token_to_use = user.expo_push_token
        
        # Fail if we don't have any token at this point
        if not token_to_use:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No push token provided and admin user has no push token registered. Please provide a push token in the request body or set up push notifications on your device."
            )
        
        print(f"[ADMIN TEST] Using push token: {token_to_use[:20]}...")
        
        # Send test notification and log it
        result = await admin_push_service.send_test_notification(token_to_use, admin_id=current_user.id)
        
        if result['success']:
            return {
                "success": True,
                "message": "Test notification sent successfully",
                "token": token_to_use[:20] + "..."
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get('message', 'Failed to send test notification')
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ====== New Admin User Management Endpoints ======

@router.get("/users/{user_id}/complete-view")
async def get_complete_user_view(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get complete user view including all related data"""
    from ..services.admin_user_service import AdminUserService
    import logging
    logger = logging.getLogger(__name__)
    try:
        logger.info(f"[admin_router] GET complete-view for user_id: {user_id}")
        admin_user_service = AdminUserService(db)
        user_data = await admin_user_service.get_complete_user_view(user_id)
        if not user_data:
            logger.warning(f"[admin_router] User not found: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")
        logger.info(f"[admin_router] Successfully retrieved complete view for user_id: {user_id}")
        return user_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[admin_router] Error in get_complete_user_view for user_id {user_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/activity-timeline")
async def get_user_activity_timeline(
    user_id: int,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get chronological activity timeline for a user"""
    from ..services.admin_user_service import AdminUserService
    try:
        admin_user_service = AdminUserService(db)
        timeline = await admin_user_service.get_user_activity_timeline(user_id, skip, limit)
        return timeline
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/files")
async def get_user_files(
    user_id: int,
    category: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get all user uploaded files, optionally filtered by category"""
    from ..services.admin_user_service import AdminUserService
    try:
        admin_user_service = AdminUserService(db)
        files = await admin_user_service.get_user_files(user_id, category)
        return files
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/kyc-history")
async def get_user_kyc_history(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get all KYC submissions for a user"""
    from ..services.admin_user_service import AdminUserService
    try:
        admin_user_service = AdminUserService(db)
        kyc_history = await admin_user_service.get_user_kyc_history(user_id)
        return {"total": len(kyc_history), "kyc_submissions": kyc_history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/disputes")
async def get_user_disputes(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get all disputes related to a user"""
    from ..services.admin_user_service import AdminUserService
    try:
        admin_user_service = AdminUserService(db)
        disputes = await admin_user_service.get_user_disputes(user_id)
        return disputes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/jobs")
async def get_user_jobs(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get all jobs posted and applied by a user"""
    from ..services.admin_user_service import AdminUserService
    try:
        admin_user_service = AdminUserService(db)
        jobs = await admin_user_service.get_user_jobs(user_id)
        return jobs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/services")
async def get_user_services(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get all services posted by a user"""
    from ..services.admin_user_service import AdminUserService
    try:
        admin_user_service = AdminUserService(db)
        services = await admin_user_service.get_user_services(user_id)
        return services
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/reviews")
async def get_user_reviews(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get reviews given and received by a user"""
    from ..services.admin_user_service import AdminUserService
    try:
        admin_user_service = AdminUserService(db)
        reviews = await admin_user_service.get_user_reviews(user_id)
        return reviews
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{user_id}/profile")
async def update_user_profile(
    user_id: int,
    updates: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Update user profile information"""
    from ..services.admin_user_service import AdminUserService
    try:
        admin_user_service = AdminUserService(db)
        result = await admin_user_service.update_user_profile(current_user.id, user_id, updates)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/account-status")
async def manage_account_status(
    user_id: int,
    request_data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Manage user account status (suspend/ban/reactivate)"""
    from ..services.admin_user_service import AdminUserService
    try:
        admin_user_service = AdminUserService(db)
        result = await admin_user_service.manage_account_status(
            current_user.id,
            user_id,
            request_data.get("status"),
            request_data.get("reason"),
            request_data.get("duration_days")
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/wallet/add-funds")
async def add_wallet_funds(
    user_id: int,
    request_data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Add funds to user wallet"""
    from ..services.admin_user_service import AdminUserService
    from decimal import Decimal
    try:
        admin_user_service = AdminUserService(db)
        result = await admin_user_service.add_wallet_funds(
            current_user.id,
            user_id,
            Decimal(str(request_data.get("amount"))),
            request_data.get("description", "Admin credit")
        )
        return result
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/{user_id}/wallet/deduct-funds")
async def deduct_wallet_funds(
    user_id: int,
    request_data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Deduct funds from user wallet"""
    from ..services.admin_user_service import AdminUserService
    from decimal import Decimal
    try:
        admin_user_service = AdminUserService(db)
        result = await admin_user_service.deduct_wallet_funds(
            current_user.id,
            user_id,
            Decimal(str(request_data.get("amount"))),
            request_data.get("description", "Admin debit")
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/auth/reset")
async def reset_user_authentication(
    user_id: int,
    request_data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Reset user authentication (password, 2FA, login attempts)"""
    from ..services.admin_user_service import AdminUserService
    try:
        admin_user_service = AdminUserService(db)
        result = await admin_user_service.reset_user_authentication(
            current_user.id,
            user_id,
            request_data.get("reset_password", False),
            request_data.get("reset_2fa", False),
            request_data.get("clear_login_attempts", False)
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/role/switch")
async def switch_user_role(
    user_id: int,
    request_data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Switch user between WORKER and EMPLOYER roles"""
    from ..services.admin_user_service import AdminUserService
    try:
        admin_user_service = AdminUserService(db)
        result = await admin_user_service.switch_user_role(
            current_user.id,
            user_id,
            request_data.get("new_role")
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/withdrawals")
async def get_user_withdrawal_requests(
    user_id: int,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get all withdrawal requests for a user"""
    from ..services.admin_withdrawal_service import AdminWithdrawalService
    try:
        withdrawal_service = AdminWithdrawalService(db)
        withdrawals = await withdrawal_service.get_user_withdrawal_requests(user_id, skip, limit)
        return withdrawals
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/withdrawals/{request_id}")
async def get_withdrawal_request_detail(
    user_id: int,
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get detailed information about a withdrawal request"""
    from ..services.admin_withdrawal_service import AdminWithdrawalService
    try:
        withdrawal_service = AdminWithdrawalService(db)
        withdrawal = await withdrawal_service.get_withdrawal_request(request_id)
        if not withdrawal:
            raise HTTPException(status_code=404, detail="Withdrawal request not found")
        return withdrawal
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/withdrawals/{request_id}/approve")
async def approve_withdrawal_request(
    user_id: int,
    request_id: int,
    request_data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Approve a withdrawal request"""
    from ..services.admin_withdrawal_service import AdminWithdrawalService
    try:
        withdrawal_service = AdminWithdrawalService(db)
        result = await withdrawal_service.approve_withdrawal(
            current_user.id,
            request_id,
            request_data.get("notes")
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/withdrawals/{request_id}/reject")
async def reject_withdrawal_request(
    user_id: int,
    request_id: int,
    request_data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Reject a withdrawal request"""
    from ..services.admin_withdrawal_service import AdminWithdrawalService
    try:
        withdrawal_service = AdminWithdrawalService(db)
        result = await withdrawal_service.reject_withdrawal(
            current_user.id,
            request_id,
            request_data.get("reason"),
            request_data.get("notes")
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/withdrawals/{request_id}/retry")
async def retry_withdrawal_request(
    user_id: int,
    request_id: int,
    request_data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Retry a failed withdrawal request"""
    from ..services.admin_withdrawal_service import AdminWithdrawalService
    try:
        withdrawal_service = AdminWithdrawalService(db)
        result = await withdrawal_service.retry_withdrawal(
            current_user.id,
            request_id,
            request_data.get("notes")
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/withdrawals/{request_id}/notes")
async def add_withdrawal_notes(
    user_id: int,
    request_id: int,
    request_data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Add or update admin notes on a withdrawal request"""
    from ..services.admin_withdrawal_service import AdminWithdrawalService
    try:
        withdrawal_service = AdminWithdrawalService(db)
        result = await withdrawal_service.add_withdrawal_notes(
            current_user.id,
            request_id,
            request_data.get("notes", "")
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/kyc")
async def get_user_kyc_submission(
    user_id: int,
    submission_id: int = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get KYC submission for a user"""
    from ..services.admin_kyc_service import AdminKYCService
    try:
        kyc_service = AdminKYCService(db)
        kyc = await kyc_service.get_user_kyc_submission(user_id, submission_id)
        if not kyc:
            raise HTTPException(status_code=404, detail="KYC submission not found")
        return kyc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/kyc/{submission_id}/approve")
async def approve_kyc_submission(
    user_id: int,
    submission_id: int,
    request_data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Approve KYC submission"""
    from ..services.admin_kyc_service import AdminKYCService
    try:
        kyc_service = AdminKYCService(db)
        result = await kyc_service.approve_kyc(
            current_user.id,
            submission_id,
            request_data.get("notes")
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/kyc/{submission_id}/reject")
async def reject_kyc_submission(
    user_id: int,
    submission_id: int,
    request_data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Reject KYC submission"""
    from ..services.admin_kyc_service import AdminKYCService
    try:
        kyc_service = AdminKYCService(db)
        result = await kyc_service.reject_kyc(
            current_user.id,
            submission_id,
            request_data.get("reason"),
            request_data.get("notes")
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/kyc/{submission_id}/request-resubmission")
async def request_kyc_resubmission(
    user_id: int,
    submission_id: int,
    request_data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Request KYC resubmission with corrections"""
    from ..services.admin_kyc_service import AdminKYCService
    try:
        kyc_service = AdminKYCService(db)
        result = await kyc_service.request_kyc_resubmission(
            current_user.id,
            submission_id,
            request_data.get("reason"),
            request_data.get("notes")
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-logs")
async def get_admin_audit_logs(
    skip: int = 0,
    limit: int = 50,
    admin_id: int = None,
    action_type: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get admin action audit logs"""
    from ..services.admin_audit_service import AdminAuditService
    try:
        audit_service = AdminAuditService(db)
        logs = await audit_service.get_admin_audit_logs(skip, limit, admin_id, action_type)
        return logs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/audit-logs")
async def get_user_audit_logs(
    user_id: int,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get all audit logs targeting a specific user"""
    from ..services.admin_audit_service import AdminAuditService
    try:
        audit_service = AdminAuditService(db)
        logs = await audit_service.get_user_audit_logs(user_id, skip, limit)
        return logs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== JOB CATEGORY MANAGEMENT ENDPOINTS ==============

@router.get("/categories", response_model=List[CategoryInDB])
async def list_all_categories(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get all job categories with pagination"""
    from ..services.category_service import CategoryService
    try:
        category_service = CategoryService(db)
        categories = await category_service.get_categories(skip, limit)
        return categories
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/categories", response_model=CategoryInDB)
async def create_category(
    category_name: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Create a new job category"""
    from ..services.category_service import CategoryService
    try:
        category_service = CategoryService(db)
        category = await category_service.create_category(category_name)
        return category
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories/{category_id}", response_model=CategoryInDB)
async def get_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Get a specific job category by ID"""
    from ..services.category_service import CategoryService
    try:
        category_service = CategoryService(db)
        category = await category_service.get_category_by_id(category_id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        return category
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/categories/{category_id}", response_model=CategoryInDB)
async def update_category(
    category_id: int,
    category_name: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Update a job category name"""
    from ..services.category_service import CategoryService
    try:
        category_service = CategoryService(db)
        category = await category_service.update_category(category_id, category_name)
        return category
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    """Delete a job category"""
    from ..services.category_service import CategoryService
    try:
        category_service = CategoryService(db)
        result = await category_service.delete_category(category_id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
