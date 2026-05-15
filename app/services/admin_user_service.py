"""
Admin user management service.
Handles all user account operations that admins can perform.
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import selectinload
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)

from app.models.user import User, UserRole
from app.models.kyc import KYCSubmission
from app.models.dispute import Dispute
from app.models.transaction import Transaction
from app.models.job import Job, JobStatus
from app.models.job_application import JobApplication
from app.models.service import Service
from app.models.review import Review
from app.models.file import File
from app.models.withdrawal_request import WithdrawalRequest
from app.models.recent_activity import RecentActivity
from app.models.payment import Payment
from app.services.admin_audit_service import AdminAuditService
from app.models.admin_audit_log import AdminActionType
from app.utils.security import get_password_hash


class AdminUserService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit_service = AdminAuditService(db)

    async def get_complete_user_view(self, user_id: int) -> Dict[str, Any]:
        """
        Get complete user information including profile, stats, KYC, disputes, etc.
        Consolidates data from multiple models for a unified admin view.
        """
        try:
            logger.info(f"[get_complete_user_view] Starting for user_id: {user_id}")
            # Get user - don't try to eager load dynamic relationships
            logger.info(f"[get_complete_user_view] Fetching user record for user_id: {user_id}")
            result = await self.db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            logger.info(f"[get_complete_user_view] User found: {user is not None}")
        
            if not user:
                logger.warning(f"[get_complete_user_view] User not found for user_id: {user_id}")
                return None
            
            # Get KYC submissions separately
            logger.info(f"[get_complete_user_view] Fetching KYC submissions")
            kyc_result = await self.db.execute(
                select(KYCSubmission).where(KYCSubmission.user_id == user_id).order_by(desc(KYCSubmission.created_at))
            )
            kyc_submissions = kyc_result.scalars().all()
            logger.info(f"[get_complete_user_view] Found {len(kyc_submissions)} KYC submissions")
        
            # Get transaction history
            logger.info(f"[get_complete_user_view] Fetching transaction history")
            transactions_result = await self.db.execute(
                select(Transaction).where(Transaction.user_id == user_id).order_by(desc(Transaction.created_at)).limit(20)
            )
            transactions = transactions_result.scalars().all()
            logger.info(f"[get_complete_user_view] Found {len(transactions)} transactions")
        
            # Get counts for dynamic relationships
            logger.info(f"[get_complete_user_view] Fetching jobs posted count")
            jobs_posted_result = await self.db.execute(
                select(func.count(Job.id)).where(Job.employer_id == user_id)
            )
            jobs_posted_count = jobs_posted_result.scalar() or 0
            logger.info(f"[get_complete_user_view] Jobs posted: {jobs_posted_count}")
        
            logger.info(f"[get_complete_user_view] Fetching jobs applied count")
            jobs_applied_result = await self.db.execute(
                select(func.count(JobApplication.id)).where(JobApplication.worker_id == user_id)
            )
            jobs_applied_count = jobs_applied_result.scalar() or 0
            logger.info(f"[get_complete_user_view] Jobs applied: {jobs_applied_count}")
        
            logger.info(f"[get_complete_user_view] Fetching services posted count")
            services_result = await self.db.execute(
                select(func.count(Service.id)).where(Service.worker_id == user_id)
            )
            services_posted_count = services_result.scalar() or 0
            logger.info(f"[get_complete_user_view] Services posted: {services_posted_count}")
        
            logger.info(f"[get_complete_user_view] Fetching reviews received count")
            reviews_received_result = await self.db.execute(
                select(func.count(Review.id)).where(Review.reviewee_id == user_id)
            )
            reviews_received_count = reviews_received_result.scalar() or 0
            logger.info(f"[get_complete_user_view] Reviews received: {reviews_received_count}")
        
            # Get disputes counts
            logger.info(f"[get_complete_user_view] Fetching disputes counts")
            disputes_claimed_result = await self.db.execute(
                select(func.count(Dispute.id)).where(Dispute.claimant_id == user_id)
            )
            disputes_claimed_count = disputes_claimed_result.scalar() or 0
            logger.info(f"[get_complete_user_view] Disputes claimed: {disputes_claimed_count}")
            
            disputes_defended_result = await self.db.execute(
                select(func.count(Dispute.id)).where(Dispute.defendant_id == user_id)
            )
            disputes_defended_count = disputes_defended_result.scalar() or 0
            logger.info(f"[get_complete_user_view] Disputes defended: {disputes_defended_count}")
            
            withdrawal_disputes_result = await self.db.execute(
                select(func.count(Dispute.id)).where(Dispute.user_id == user_id)
            )
            withdrawal_disputes_count = withdrawal_disputes_result.scalar() or 0
            logger.info(f"[get_complete_user_view] Withdrawal disputes: {withdrawal_disputes_count}")
            
            disputes_count = disputes_claimed_count + disputes_defended_count + withdrawal_disputes_count
            logger.info(f"[get_complete_user_view] Total disputes: {disputes_count}")
            
            # Get wallet balance
            logger.info(f"[get_complete_user_view] Processing wallet balance")
            wallet_balance = float(user.wallet_balance) if user.wallet_balance else 0.0
        
            # Current KYC status
            logger.info(f"[get_complete_user_view] Processing KYC submission")
            kyc_submission = None
            if kyc_submissions:
                kyc_submission = {
                    "id": kyc_submissions[0].id,
                    "status": kyc_submissions[0].status,
                    "document_type": kyc_submissions[0].document_type,
                    "created_at": kyc_submissions[0].created_at.isoformat() if kyc_submissions[0].created_at else None,
                    "verified_at": kyc_submissions[0].verified_at.isoformat() if kyc_submissions[0].verified_at else None,
                }
            
            logger.info(f"[get_complete_user_view] Calculating profile completion")
            profile_completion = self._calculate_profile_completion(user)
            logger.info(f"[get_complete_user_view] Profile completion: {profile_completion}")
            
            logger.info(f"[get_complete_user_view] Building response dictionary")
            try:
                response_data = {
                    "id": user.id,
                    "email": user.email,
                    "phone": user.phone,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.role.value,
                    "is_active": user.is_active,
                    "is_verified": user.is_verified,
                    "is_email_verified": user.is_email_verified,
                    "is_kyc_verified": user.is_kyc_verified,
                    "kyc_status": user.kyc_status,
                    "avatar_url": user.avatar_url,
                    "reputation_score": float(user.reputation_score) if user.reputation_score else 0.0,
                    "wallet_balance": wallet_balance,
                    "subscription_status": user.subscription_status,
                    "subscription_expiry": user.subscription_expiry.isoformat() if user.subscription_expiry else None,
                    "is_2fa_enabled": user.is_2fa_enabled,
                    "failed_login_attempts": user.failed_login_attempts,
                    "lockout_until": user.lockout_until.isoformat() if user.lockout_until else None,
                    # Worker-specific fields
                    "headline": user.headline,
                    "location": user.location,
                    "about_me": user.about_me,
                    "skills": user.skills,
                    "experience_level": user.experience_level,
                    # Stats
                    "stats": {
                        "jobs_posted": jobs_posted_count,
                        "jobs_applied": jobs_applied_count,
                        "services_posted": services_posted_count,
                        "reviews_received": reviews_received_count,
                        "disputes_count": disputes_count,
                        "profile_completion": profile_completion,
                    },
                    "kyc": kyc_submission,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                    "updated_at": user.updated_at.isoformat() if user.updated_at else None,
                }
                logger.info(f"[get_complete_user_view] Response built successfully")
                return response_data
            except Exception as response_error:
                logger.error(f"[get_complete_user_view] Error building response: {type(response_error).__name__}: {str(response_error)}", exc_info=True)
                raise
        except Exception as e:
            logger.error(f"[get_complete_user_view] Unexpected error for user_id {user_id}: {type(e).__name__}: {str(e)}", exc_info=True)
            raise

    async def get_user_activity_timeline(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Get chronological timeline of all user activities"""
        query = select(RecentActivity).where(
            RecentActivity.user_id == user_id
        ).order_by(desc(RecentActivity.timestamp))
        
        total_result = await self.db.execute(
            select(func.count(RecentActivity.id)).where(RecentActivity.user_id == user_id)
        )
        total = total_result.scalar() or 0
        
        result = await self.db.execute(query.offset(skip).limit(limit))
        activities = result.scalars().all()
        
        activities_data = []
        for activity in activities:
            activities_data.append({
                "id": activity.id,
                "activity_type": activity.activity_type.value if hasattr(activity.activity_type, 'value') else str(activity.activity_type),
                "description": activity.description,
                "related_entity_type": activity.related_entity_type,
                "related_entity_id": activity.related_entity_id,
                "timestamp": activity.timestamp.isoformat() if activity.timestamp else None,
                "activity_data": activity.activity_data,
            })
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": activities_data,
        }

    async def get_user_files(
        self,
        user_id: int,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get all user uploaded files, optionally filtered by category"""
        query = select(File).where(File.user_id == user_id)
        
        if category:
            query = query.where(File.category == category)
        
        query = query.order_by(desc(File.created_at))
        result = await self.db.execute(query)
        files = result.scalars().all()
        
        # Group files by category
        files_by_category = {}
        for file in files:
            cat = file.category.value if hasattr(file.category, 'value') else str(file.category)
            if cat not in files_by_category:
                files_by_category[cat] = []
            files_by_category[cat].append({
                "id": file.id,
                "filename": file.filename,
                "original_filename": file.original_filename,
                "file_path": file.file_path,
                "file_type": file.file_type,
                "file_size": file.file_size,
                "category": cat,
                "reference_id": file.reference_id,
                "reference_type": file.reference_type,
                "created_at": file.created_at.isoformat() if file.created_at else None,
            })
        
        return {
            "files_by_category": files_by_category,
            "total_files": len(files),
        }

    async def get_user_kyc_history(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all KYC submissions for a user"""
        result = await self.db.execute(
            select(KYCSubmission).where(
                KYCSubmission.user_id == user_id
            ).order_by(desc(KYCSubmission.created_at))
        )
        submissions = result.scalars().all()
        
        kyc_data = []
        for submission in submissions:
            kyc_data.append({
                "id": submission.id,
                "document_type": submission.document_type,
                "status": submission.status,
                "document_path": submission.document_path,
                "selfie_path": submission.selfie_path,
                "notes": submission.notes,
                "created_at": submission.created_at.isoformat() if submission.created_at else None,
                "verified_at": submission.verified_at.isoformat() if submission.verified_at else None,
            })
        
        return kyc_data

    async def get_user_disputes(self, user_id: int) -> Dict[str, Any]:
        """Get all disputes related to a user"""
        # Get all disputes where user is involved
        result = await self.db.execute(
            select(Dispute).where(
                (Dispute.claimant_id == user_id) |
                (Dispute.defendant_id == user_id) |
                (Dispute.user_id == user_id)
            ).order_by(desc(Dispute.created_at))
        )
        disputes = result.scalars().all()
        
        disputes_data = []
        for dispute in disputes:
            disputes_data.append({
                "id": dispute.id,
                "dispute_type": dispute.dispute_type.value if hasattr(dispute.dispute_type, 'value') else str(dispute.dispute_type),
                "status": dispute.status.value if hasattr(dispute.status, 'value') else str(dispute.status),
                "claimant_id": dispute.claimant_id,
                "defendant_id": dispute.defendant_id,
                "reason": dispute.reason,
                "resolution": dispute.resolution,
                "created_at": dispute.created_at.isoformat() if dispute.created_at else None,
                "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None,
            })
        
        return {
            "total": len(disputes_data),
            "disputes": disputes_data,
        }

    async def get_user_jobs(self, user_id: int) -> Dict[str, Any]:
        """Get all jobs posted and applied by a user"""
        # Jobs posted
        posted_result = await self.db.execute(
            select(Job).where(Job.employer_id == user_id).order_by(desc(Job.created_at))
        )
        jobs_posted = posted_result.scalars().all()
        
        # Jobs applied to
        applied_result = await self.db.execute(
            select(JobApplication).where(JobApplication.worker_id == user_id).order_by(desc(JobApplication.created_at))
        )
        jobs_applied = applied_result.scalars().all()
        
        posted_data = []
        for job in jobs_posted:
            job_price = float(job.job_price) if job.job_price is not None else None
            posted_data.append({
                "id": job.id,
                "title": job.title,
                "status": job.status.value if hasattr(job.status, 'value') else str(job.status),
                "job_price": job_price,
                "budget": job_price,  # legacy alias
                "created_at": job.created_at.isoformat() if job.created_at else None,
            })
        
        applied_data = []
        for app in jobs_applied:
            applied_data.append({
                "id": app.id,
                "job_id": app.job_id,
                "job_title": app.job.title if app.job else "Unknown",
                "status": app.status.value if hasattr(app.status, 'value') else str(app.status),
                "applied_at": app.created_at.isoformat() if app.created_at else None,
            })
        
        return {
            "jobs_posted": posted_data,
            "jobs_applied": applied_data,
        }

    async def get_user_services(self, user_id: int) -> Dict[str, Any]:
        """Get services posted by a user"""
        result = await self.db.execute(
            select(Service).where(Service.worker_id == user_id).order_by(desc(Service.created_at))
        )
        services = result.scalars().all()
        
        services_data = []
        for service in services:
            services_data.append({
                "id": service.id,
                "title": service.title,
                "description": service.description,
                "category": service.category,
                "price": float(service.price) if service.price else 0.0,
                "delivery_days": service.delivery_days,
                "revisions": service.revisions,
                "created_at": service.created_at.isoformat() if service.created_at else None,
            })
        
        return {
            "total": len(services_data),
            "services": services_data,
        }

    async def get_user_reviews(self, user_id: int) -> Dict[str, Any]:
        """Get reviews given and received by a user"""
        # Reviews given
        given_result = await self.db.execute(
            select(Review).where(Review.reviewer_id == user_id).order_by(desc(Review.created_at))
        )
        reviews_given = given_result.scalars().all()
        
        # Reviews received
        received_result = await self.db.execute(
            select(Review).where(Review.reviewee_id == user_id).order_by(desc(Review.created_at))
        )
        reviews_received = received_result.scalars().all()
        
        given_data = [
            {
                "id": r.id,
                "rating": r.rating,
                "comment": r.comment,
                "reviewee_id": r.reviewee_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reviews_given
        ]
        
        received_data = [
            {
                "id": r.id,
                "rating": r.rating,
                "comment": r.comment,
                "reviewer_id": r.reviewer_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reviews_received
        ]
        
        return {
            "reviews_given": given_data,
            "reviews_received": received_data,
            "average_rating": sum([r.rating for r in reviews_received]) / len(reviews_received) if reviews_received else 0.0,
        }

    async def update_user_profile(
        self,
        admin_id: int,
        user_id: int,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update user profile information"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        old_values = {}
        new_values = {}
        
        # Allowed fields to update
        allowed_fields = {
            "first_name", "last_name", "email", "phone", "avatar_url",
            "location", "headline", "about_me", "skills", "experience_level"
        }
        
        for field, value in updates.items():
            if field in allowed_fields and hasattr(user, field):
                old_values[field] = getattr(user, field)
                setattr(user, field, value)
                new_values[field] = value
        
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        # Log the action
        await self.audit_service.log_action(
            admin_id=admin_id,
            action_type=AdminActionType.PROFILE_UPDATE,
            target_user_id=user_id,
            description=f"Updated user profile",
            old_values=old_values,
            new_values=new_values,
        )
        
        return {"success": True, "message": "User profile updated", "user_id": user_id}

    async def manage_account_status(
        self,
        admin_id: int,
        user_id: int,
        status: str,
        reason: Optional[str] = None,
        duration_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Manage user account status: activate, suspend, or ban.
        status: "active", "suspended", "banned"
        """
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        old_is_active = user.is_active
        old_lockout = user.lockout_until
        
        if status == "active":
            user.is_active = True
            user.lockout_until = None
        elif status == "suspended":
            user.is_active = False
            if duration_days:
                user.lockout_until = datetime.utcnow() + timedelta(days=duration_days)
        elif status == "banned":
            user.is_active = False
            user.lockout_until = None  # Permanent ban
        
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        # Log the action
        await self.audit_service.log_action(
            admin_id=admin_id,
            action_type=AdminActionType.ACCOUNT_STATUS_CHANGE,
            target_user_id=user_id,
            description=f"Changed account status to {status}. Reason: {reason or 'Not provided'}",
            old_values={"is_active": old_is_active, "lockout_until": old_lockout.isoformat() if old_lockout else None},
            new_values={"is_active": user.is_active, "lockout_until": user.lockout_until.isoformat() if user.lockout_until else None},
            context_data={"reason": reason, "duration_days": duration_days},
        )
        
        return {
            "success": True,
            "message": f"Account status changed to {status}",
            "user_id": user_id,
            "new_status": status,
        }

    async def add_wallet_funds(
        self,
        admin_id: int,
        user_id: int,
        amount: Decimal,
        description: str,
    ) -> Dict[str, Any]:
        """Add funds to user wallet"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        old_balance = Decimal(str(user.wallet_balance))
        user.wallet_balance = Decimal(str(user.wallet_balance)) + amount
        
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        # Log the action
        await self.audit_service.log_action(
            admin_id=admin_id,
            action_type=AdminActionType.WALLET_ADD_FUNDS,
            target_user_id=user_id,
            description=f"Added ₦{amount} to wallet. {description}",
            old_values={"wallet_balance": float(old_balance)},
            new_values={"wallet_balance": float(user.wallet_balance)},
            context_data={"amount": float(amount), "reason": description},
        )
        
        return {
            "success": True,
            "message": "Funds added to wallet",
            "user_id": user_id,
            "new_balance": float(user.wallet_balance),
            "amount_added": float(amount),
        }

    async def deduct_wallet_funds(
        self,
        admin_id: int,
        user_id: int,
        amount: Decimal,
        description: str,
    ) -> Dict[str, Any]:
        """Deduct funds from user wallet"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        if Decimal(str(user.wallet_balance)) < amount:
            raise ValueError(f"Insufficient balance. Current: ₦{user.wallet_balance}, Required: ₦{amount}")
        
        old_balance = Decimal(str(user.wallet_balance))
        user.wallet_balance = Decimal(str(user.wallet_balance)) - amount
        
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        # Log the action
        await self.audit_service.log_action(
            admin_id=admin_id,
            action_type=AdminActionType.WALLET_DEDUCT_FUNDS,
            target_user_id=user_id,
            description=f"Deducted ₦{amount} from wallet. {description}",
            old_values={"wallet_balance": float(old_balance)},
            new_values={"wallet_balance": float(user.wallet_balance)},
            context_data={"amount": float(amount), "reason": description},
        )
        
        return {
            "success": True,
            "message": "Funds deducted from wallet",
            "user_id": user_id,
            "new_balance": float(user.wallet_balance),
            "amount_deducted": float(amount),
        }

    async def reset_user_authentication(
        self,
        admin_id: int,
        user_id: int,
        reset_password: bool = False,
        reset_2fa: bool = False,
        clear_login_attempts: bool = False,
    ) -> Dict[str, Any]:
        """Reset user authentication settings"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        old_values = {
            "failed_login_attempts": user.failed_login_attempts,
            "is_2fa_enabled": user.is_2fa_enabled,
            "lockout_until": user.lockout_until.isoformat() if user.lockout_until else None,
        }
        
        if reset_password:
            # Generate temporary password (in real implementation, send via email)
            user.hashed_password = get_password_hash("TemporaryPassword123!")
        
        if reset_2fa:
            user.is_2fa_enabled = False
            user.otp_secret = None
        
        if clear_login_attempts:
            user.failed_login_attempts = 0
            user.lockout_until = None
        
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        new_values = {
            "failed_login_attempts": user.failed_login_attempts,
            "is_2fa_enabled": user.is_2fa_enabled,
            "lockout_until": user.lockout_until.isoformat() if user.lockout_until else None,
        }
        
        # Log the action
        await self.audit_service.log_action(
            admin_id=admin_id,
            action_type=AdminActionType.AUTHENTICATION_RESET,
            target_user_id=user_id,
            description=f"Reset authentication - Password: {reset_password}, 2FA: {reset_2fa}, Login attempts: {clear_login_attempts}",
            old_values=old_values,
            new_values=new_values,
            context_data={
                "reset_password": reset_password,
                "reset_2fa": reset_2fa,
                "clear_login_attempts": clear_login_attempts,
            },
        )
        
        return {
            "success": True,
            "message": "User authentication reset",
            "user_id": user_id,
            "reset_items": {
                "password_reset": reset_password,
                "2fa_reset": reset_2fa,
                "login_attempts_cleared": clear_login_attempts,
            },
        }

    async def switch_user_role(
        self,
        admin_id: int,
        user_id: int,
        new_role: str,
    ) -> Dict[str, Any]:
        """Switch user between EMPLOYER and WORKER roles"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        if user.role == UserRole.ADMIN:
            raise ValueError("Cannot change ADMIN role")
        
        old_role = user.role
        
        # Convert string to UserRole enum
        if new_role.upper() == "WORKER":
            user.role = UserRole.WORKER
        elif new_role.upper() == "EMPLOYER":
            user.role = UserRole.EMPLOYER
        else:
            raise ValueError(f"Invalid role: {new_role}")
        
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        # Log the action
        await self.audit_service.log_action(
            admin_id=admin_id,
            action_type=AdminActionType.ROLE_SWITCH,
            target_user_id=user_id,
            description=f"Switched user role from {old_role.value} to {user.role.value}",
            old_values={"role": old_role.value},
            new_values={"role": user.role.value},
        )
        
        return {
            "success": True,
            "message": f"User role switched to {new_role}",
            "user_id": user_id,
            "old_role": old_role.value,
            "new_role": user.role.value,
        }

    def _calculate_profile_completion(self, user: User) -> float:
        """Calculate profile completion percentage"""
        fields = [
            user.first_name,
            user.last_name,
            user.phone,
            user.location,
            user.avatar_url,
            user.is_verified,
            user.is_kyc_verified,
        ]
        
        if user.role == UserRole.WORKER:
            fields.extend([
                user.headline,
                user.about_me,
                user.experience_level,
                user.skills,
            ])
        
        completed = sum(1 for f in fields if f)
        return (completed / len(fields) * 100) if fields else 0.0
