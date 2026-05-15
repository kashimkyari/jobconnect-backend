from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from typing import List, Optional
from sqlalchemy.orm import selectinload
from datetime import datetime

from ..models.user import User
from ..models.kyc import KYCSubmission
from ..schemas.kyc import (
    KYCSubmission as KYCSubmissionSchema,
    KYCVerification,
    KYCStatus,
    KYCSubmissionCreate,
)
from ..utils.logging import StructuredLogger
from .recent_activity_service import RecentActivityService
from .badge_service import BadgeService
from ..schemas.recent_activity import RecentActivityCreate
from datetime import datetime

logger = StructuredLogger("kyc")

class KYCService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_verification(
        self, user_id: int, submission_data: KYCSubmissionCreate
    ) -> KYCSubmissionSchema:
        # Check for an existing pending submission
        query = select(KYCSubmission).where(
            KYCSubmission.user_id == user_id,
            KYCSubmission.status == "pending"
        )
        result = await self.db.execute(query)
        existing_submission = result.scalars().first()

        if existing_submission:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You already have a pending KYC submission. Please wait for it to be reviewed."
            )

        import json
        
        # Store all selfies as a JSON string for full liveness review
        selfie_data = json.dumps(submission_data.selfie_paths) if submission_data.selfie_paths else submission_data.selfie_path

        # Create KYC submission record
        submission = KYCSubmission(
            user_id=user_id,
            document_type=submission_data.document_type,
            document_path=submission_data.document_path,
            selfie_path=selfie_data,
            status="pending",
        )

        self.db.add(submission)
        
        # Update user's kyc_status to pending
        user = await self.db.get(User, user_id)
        if user:
            user.kyc_status = "pending"
            
        await self.db.commit()
        
        # Re-fetch the submission with the user relationship eagerly loaded
        # to prevent lazy loading issues during serialization.
        result = await self.db.execute(
            select(KYCSubmission)
            .options(selectinload(KYCSubmission.user))
            .filter(KYCSubmission.id == submission.id)
        )
        refreshed_submission = result.scalar_one()
        
        return refreshed_submission

    async def verify_submission(
        self,
        submission_id: int,
        verification: KYCVerification
    ) -> KYCSubmission:
        query = select(KYCSubmission).options(selectinload(KYCSubmission.user)).filter(KYCSubmission.id == submission_id)
        result = await self.db.execute(query)
        submission = result.scalar_one_or_none()
        if not submission:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
            
        # Update submission status
        submission.status = "approved" if verification.is_approved else "rejected"
        submission.notes = verification.notes
        submission.verified_at = datetime.utcnow()
        
        # If approved, update user verification status
        user = await self.db.get(User, submission.user_id)
        if user:
            if verification.is_approved:
                user.is_kyc_verified = True
                user.kyc_status = "verified"
                
                # Auto-award KYC Verified badge
                badge_service = BadgeService(self.db)
                award_result = await badge_service.auto_award_badges(submission.user_id)
                logger.info(f"Auto-award badges result for user {submission.user_id}: {award_result}")
            else:
                user.kyc_status = "rejected"
                
        await self.db.commit()
        
        # Re-fetch the submission with the user relationship eagerly loaded
        # to prevent lazy loading issues during serialization after commit.
        result = await self.db.execute(
            select(KYCSubmission)
            .options(selectinload(KYCSubmission.user))
            .filter(KYCSubmission.id == submission_id)
        )
        refreshed_submission = result.scalar_one()
        
        return refreshed_submission

    async def get_verification_status(self, user_id: int) -> KYCStatus:
        # Get latest submission
        query = (
            select(KYCSubmission)
            .where(KYCSubmission.user_id == user_id)
            .order_by(desc(KYCSubmission.created_at))
        )
        result = await self.db.execute(query)
        submission = result.scalars().first()
        
        user = await self.db.get(User, user_id)
        
        if not submission:
            return KYCStatus(
                is_verified=user.is_kyc_verified if user else False,
                kyc_status=user.kyc_status if user else "not_submitted",
                latest_submission=None,
                total_attempts=0,
                last_verification_date=None,
            )

        history = await self.get_user_verification_history(user_id)

        return KYCStatus(
            is_verified=user.is_kyc_verified if user else False,
            kyc_status=user.kyc_status if user else "not_started",
            latest_submission=submission,
            total_attempts=len(history),
            last_verification_date=submission.verified_at,
        )

    async def get_pending_submissions(
        self,
        skip: int = 0,
        limit: int = 10
    ) -> List[KYCSubmissionSchema]:
        query = (
            select(KYCSubmission)
            .where(KYCSubmission.status == "pending")
            .order_by(desc(KYCSubmission.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_user_verification_history(
        self,
        user_id: int
    ) -> List[KYCSubmissionSchema]:
        query = (
            select(KYCSubmission)
            .where(KYCSubmission.user_id == user_id)
            .order_by(desc(KYCSubmission.created_at))
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_submission_by_id(self, submission_id: int) -> Optional[KYCSubmission]:
        query = select(KYCSubmission).options(selectinload(KYCSubmission.user)).filter(KYCSubmission.id == submission_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_kyc_status(self, user_id: int) -> bool:
        kyc_status = await self.get_verification_status(user_id)
        return kyc_status.is_verified
