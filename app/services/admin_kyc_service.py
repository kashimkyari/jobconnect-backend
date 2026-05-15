"""
Admin KYC management service.
Handles KYC verification, rejection, and resubmission requests.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from sqlalchemy.orm import selectinload
from typing import Optional, Dict, Any

from app.models.kyc import KYCSubmission
from app.models.user import User
from app.services.admin_audit_service import AdminAuditService
from app.models.admin_audit_log import AdminActionType
from app.utils.email import send_email
from datetime import datetime


class AdminKYCService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit_service = AdminAuditService(db)

    async def get_user_kyc_submission(
        self,
        user_id: int,
        submission_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get KYC submission for a user.
        If submission_id is provided, get specific submission.
        Otherwise, get the most recent one.
        """
        if submission_id:
            result = await self.db.execute(
                select(KYCSubmission).where(
                    (KYCSubmission.id == submission_id) &
                    (KYCSubmission.user_id == user_id)
                ).options(
                    selectinload(KYCSubmission.user),
                )
            )
        else:
            result = await self.db.execute(
                select(KYCSubmission).where(
                    KYCSubmission.user_id == user_id
                ).order_by(desc(KYCSubmission.created_at)).options(
                    selectinload(KYCSubmission.user),
                )
            )
            result = await self.db.execute(
                select(KYCSubmission).where(
                    KYCSubmission.user_id == user_id
                ).order_by(desc(KYCSubmission.created_at)).limit(1)
            )
        
        submission = result.scalars().first() if not submission_id else result.scalar_one_or_none()
        
        if not submission:
            return None
        
        return {
            "id": submission.id,
            "user_id": submission.user_id,
            "user": {
                "id": submission.user.id,
                "first_name": submission.user.first_name,
                "last_name": submission.user.last_name,
                "email": submission.user.email,
                "phone": submission.user.phone,
            } if submission.user else None,
            "document_type": submission.document_type,
            "document_path": submission.document_path,
            "selfie_path": submission.selfie_path,
            "status": submission.status,
            "notes": submission.notes,
            "created_at": submission.created_at.isoformat() if submission.created_at else None,
            "verified_at": submission.verified_at.isoformat() if submission.verified_at else None,
        }

    async def approve_kyc(
        self,
        admin_id: int,
        submission_id: int,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approve KYC submission"""
        result = await self.db.execute(
            select(KYCSubmission).where(
                KYCSubmission.id == submission_id
            ).options(
                selectinload(KYCSubmission.user),
            )
        )
        submission = result.scalar_one_or_none()
        
        if not submission:
            raise ValueError(f"KYC submission {submission_id} not found")
        
        if submission.status == "approved":
            raise ValueError("KYC already approved")
        
        old_status = submission.status
        submission.status = "approved"
        submission.verified_at = datetime.utcnow()
        submission.notes = notes
        
        self.db.add(submission)
        
        # Update user KYC status
        user = submission.user
        user.is_kyc_verified = True
        user.kyc_status = "approved"
        self.db.add(user)
        
        await self.db.commit()
        await self.db.refresh(submission)
        
        # Log the action
        await self.audit_service.log_action(
            admin_id=admin_id,
            action_type=AdminActionType.KYC_APPROVED,
            target_user_id=submission.user_id,
            target_entity_type="kyc_submission",
            target_entity_id=submission_id,
            description=f"Approved KYC submission (Document: {submission.document_type})",
            old_values={"status": old_status, "user_kyc_status": "not_approved"},
            new_values={"status": "approved", "user_kyc_status": "approved"},
            context_data={"document_type": submission.document_type, "notes": notes},
        )
        
        # Send notification email to user
        try:
            await send_email(
                recipient=user.email,
                subject="KYC Verification Approved",
                body=f"""
Congratulations! Your KYC verification has been approved.
You can now enjoy full access to all platform features.
""",
            )
        except Exception as e:
            print(f"Failed to send approval email: {e}")
        
        return {
            "success": True,
            "message": "KYC submission approved",
            "submission_id": submission_id,
            "user_id": submission.user_id,
        }

    async def reject_kyc(
        self,
        admin_id: int,
        submission_id: int,
        reason: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reject KYC submission"""
        result = await self.db.execute(
            select(KYCSubmission).where(
                KYCSubmission.id == submission_id
            ).options(
                selectinload(KYCSubmission.user),
            )
        )
        submission = result.scalar_one_or_none()
        
        if not submission:
            raise ValueError(f"KYC submission {submission_id} not found")
        
        if submission.status == "rejected":
            raise ValueError("KYC already rejected")
        
        old_status = submission.status
        submission.status = "rejected"
        submission.notes = f"Rejected: {reason}. {notes or ''}"
        
        self.db.add(submission)
        
        # Update user KYC status
        user = submission.user
        user.is_kyc_verified = False
        user.kyc_status = "rejected"
        self.db.add(user)
        
        await self.db.commit()
        await self.db.refresh(submission)
        
        # Log the action
        await self.audit_service.log_action(
            admin_id=admin_id,
            action_type=AdminActionType.KYC_REJECTED,
            target_user_id=submission.user_id,
            target_entity_type="kyc_submission",
            target_entity_id=submission_id,
            description=f"Rejected KYC submission (Document: {submission.document_type}). Reason: {reason}",
            old_values={"status": old_status},
            new_values={"status": "rejected"},
            context_data={"document_type": submission.document_type, "reason": reason, "notes": notes},
        )
        
        # Send notification email to user
        try:
            await send_email(
                recipient=user.email,
                subject="KYC Verification Rejected",
                body=f"""
Your KYC verification has been rejected.
Reason: {reason}

Please resubmit with clear and valid documents to proceed.
""",
            )
        except Exception as e:
            print(f"Failed to send rejection email: {e}")
        
        return {
            "success": True,
            "message": "KYC submission rejected",
            "submission_id": submission_id,
            "user_id": submission.user_id,
        }

    async def request_kyc_resubmission(
        self,
        admin_id: int,
        submission_id: int,
        reason: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Request user to resubmit KYC with corrections"""
        result = await self.db.execute(
            select(KYCSubmission).where(
                KYCSubmission.id == submission_id
            ).options(
                selectinload(KYCSubmission.user),
            )
        )
        submission = result.scalar_one_or_none()
        
        if not submission:
            raise ValueError(f"KYC submission {submission_id} not found")
        
        submission.status = "resubmission_requested"
        submission.notes = f"Resubmission requested: {reason}. {notes or ''}"
        
        self.db.add(submission)
        
        # Update user KYC status
        user = submission.user
        user.kyc_status = "resubmission_requested"
        self.db.add(user)
        
        await self.db.commit()
        await self.db.refresh(submission)
        
        # Log the action
        await self.audit_service.log_action(
            admin_id=admin_id,
            action_type=AdminActionType.KYC_RESUBMISSION_REQUESTED,
            target_user_id=submission.user_id,
            target_entity_type="kyc_submission",
            target_entity_id=submission_id,
            description=f"Requested KYC resubmission. Reason: {reason}",
            old_values={"status": submission.status},
            new_values={"status": "resubmission_requested"},
            context_data={"document_type": submission.document_type, "reason": reason, "notes": notes},
        )
        
        # Send notification email to user
        try:
            await send_email(
                recipient=user.email,
                subject="KYC Resubmission Required",
                body=f"""
Your KYC submission needs to be corrected and resubmitted.
Reason: {reason}

{notes or 'Please ensure all documents are clear and valid.'}

Please log in and resubmit your documents.
""",
            )
        except Exception as e:
            print(f"Failed to send resubmission email: {e}")
        
        return {
            "success": True,
            "message": "KYC resubmission requested",
            "submission_id": submission_id,
            "user_id": submission.user_id,
        }
