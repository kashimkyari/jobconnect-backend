from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    BackgroundTasks,
    File,
    UploadFile,
    Form,
    Header
)
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
import json
import redis

from ..models.user import User, UserRole
from ..schemas.kyc import KYCSubmission, KYCVerification, KYCStatus, KYCSubmissionCreate
from ..services.kyc_service import KYCService
from ..database import get_db
from ..utils.security import get_current_user, check_permissions
from ..utils.email_service import EmailService
from ..config import settings

router = APIRouter()

# Initialize Redis for session state (liveness step tracking)
try:
    _redis_client = redis.from_url(settings.REDIS_URL)
except Exception:
    _redis_client = None

# Initialize Redis for session state (liveness step tracking)
try:
    _redis_client = redis.from_url(settings.REDIS_URL)
except Exception:
    _redis_client = None



@router.post("/submit", response_model=KYCSubmission)
async def submit_kyc(
    submission_data: KYCSubmissionCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    kyc_service = KYCService(db)
    submission = await kyc_service.submit_verification(
        user_id=current_user.id,
        submission_data=submission_data
    )
    
    # Notify admin
    admin_email = "admin@jobconnect.com"  # Replace with actual admin email
    email_service = EmailService()
    background_tasks.add_task(
        email_service.send_template_email,
        to_email=admin_email,
        template_name='plain_wrapper.html',
        subject="New KYC Submission",
        context={
            'title': "New KYC Submission",
            'message': f"User {current_user.email} has submitted KYC documents for verification."
        }
    )
    
    return submission

@router.get("/status", response_model=KYCStatus)
async def get_kyc_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    kyc_service = KYCService(db)
    status = await kyc_service.get_verification_status(current_user.id)
    return status

@router.post("/{submission_id}/verify", response_model=KYCVerification)
async def verify_kyc(
    submission_id: int,
    verification: KYCVerification,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db)
):
    kyc_service = KYCService(db)
    result = await kyc_service.verify_submission(submission_id, verification)
    
    # Notify user
    if result.user:
        status_text = "approved" if result.is_approved else "rejected"
        email_service = EmailService()
        background_tasks.add_task(
            email_service.send_kyc_verification_update,
            to_email=result.user.email,
            first_name=result.user.first_name,
            status=status_text,
            status_label=status_text.title(),
            submission_date=datetime.now().strftime("%Y-%m-%d"),
            reviewed_date=datetime.now().strftime("%Y-%m-%d"),
            feedback=verification.notes,
            dashboard_url=f"{settings.API_BASE_URL}/dashboard"
        )
    
    return result

@router.get("/pending", response_model=List[KYCSubmission])
async def get_pending_verifications(
    skip: int = 0,
    limit: int = 10,
    current_user: User = Depends(check_permissions(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db)
):
    kyc_service = KYCService(db)
    submissions = await kyc_service.get_pending_submissions(skip, limit)
    return submissions

@router.get("/{submission_id}", response_model=KYCSubmission)
async def get_submission(
    submission_id: int,
    current_user: User = Depends(check_permissions(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db)
):
    kyc_service = KYCService(db)
    submission = await kyc_service.get_submission_by_id(submission_id)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    return submission

@router.get("/history/{user_id}", response_model=List[KYCSubmission])
async def get_user_kyc_history(
    user_id: int,
    current_user: User = Depends(check_permissions(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db)
):
    kyc_service = KYCService(db)
    history = await kyc_service.get_user_verification_history(user_id)
    return history
