"""
Contract Service - Manages contract lifecycle without explicit Contract model.
Maps to JobApplication + Job model with contract_status tracking.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func, desc
from sqlalchemy.orm import selectinload, joinedload
from fastapi import HTTPException, status
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ..models.job import Job, JobStatus
from ..models.job_application import JobApplication, ApplicationStatus, ContractStatus
from ..models.user import User, UserRole
from ..models.review import Review
from ..models.transaction import Transaction, TransactionType, TransactionStatus
from ..models.payment import Payment, PaymentStatus
from ..schemas.job_application import JobApplicationInDB
from ..schemas.job import JobInDB
from ..services.notification_service import NotificationService
from ..services.review_service import ReviewService
from ..services.user_service import UserService
from ..schemas.notification import NotificationCreate
from ..models.notification import NotificationCategory
from ..utils.logging import StructuredLogger
from ..schemas.file import FileInDB
from ..websocket_manager import manager as ws_manager

logger = StructuredLogger(__name__)


class ContractService:
    """
    Service for managing contract lifecycle.
    
    Contract = accepted JobApplication + Job with status tracking.
    Statuses: PENDING -> SENT -> ACCEPTED (work starts) -> completion flow
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _release_contract_payment_if_ready(self, application: JobApplication) -> Decimal:
        """
        Release funds to worker if not already released.
        Uses escrow hold transaction when available; falls back to direct transfer for legacy jobs.
        Returns released amount.
        """
        # Already released? idempotent return.
        existing_release = await self.db.execute(
            select(Transaction).where(
                Transaction.reference.like(f"job_payment_{application.job_id}_worker_%"),
                Transaction.transaction_type == TransactionType.ESCROW_RELEASE.value,
                Transaction.status == TransactionStatus.SUCCESS
            )
        )
        existing_release_txn = existing_release.scalar_one_or_none()
        if existing_release_txn:
            return Decimal(str(existing_release_txn.amount))

        # Prefer escrow hold created at hire time.
        hold_result = await self.db.execute(
            select(Transaction).where(
                Transaction.reference == f"job_escrow_{application.job_id}_hire",
                Transaction.transaction_type == TransactionType.ESCROW_HOLD.value,
                Transaction.status == TransactionStatus.PENDING
            )
        )
        hold_txn = hold_result.scalar_one_or_none()

        worker = await self.db.get(User, application.worker_id)
        if not worker:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

        timestamp = int(datetime.utcnow().timestamp())
        if hold_txn:
            amount = abs(hold_txn.amount)
            worker.wallet_balance += amount
            self.db.add(
                Transaction(
                    user_id=worker.id,
                    job_id=application.job_id,
                    amount=amount,
                    status=TransactionStatus.SUCCESS,
                    reference=f"job_payment_{application.job_id}_worker_{timestamp}",
                    related_transaction_id=hold_txn.id,
                    description=f"Received payment for job: {application.job.title}",
                    transaction_type=TransactionType.ESCROW_RELEASE.value,
                )
            )
            hold_txn.status = TransactionStatus.SUCCESS
            return Decimal(str(amount))

        # Legacy fallback: no escrow hold exists; charge employer now.
        employer = await self.db.get(User, application.job.employer_id)
        if not employer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employer not found")

        job_cost = Decimal(str(application.job.confirmed_price or application.proposed_budget or application.job.job_price))
        if employer.wallet_balance < job_cost:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient funds in wallet. Please fund your wallet to complete this job."
            )

        employer.wallet_balance -= job_cost
        worker.wallet_balance += job_cost
        self.db.add(
            Transaction(
                user_id=employer.id,
                job_id=application.job_id,
                amount=-job_cost,
                status=TransactionStatus.SUCCESS,
                reference=f"job_payment_{application.job_id}_employer_{timestamp}",
                description=f"Payment for job: {application.job.title}",
                transaction_type=TransactionType.ESCROW_RELEASE.value,
            )
        )
        self.db.add(
            Transaction(
                user_id=worker.id,
                job_id=application.job_id,
                amount=job_cost,
                status=TransactionStatus.SUCCESS,
                reference=f"job_payment_{application.job_id}_worker_{timestamp}",
                description=f"Earned from job: {application.job.title}",
                transaction_type=TransactionType.ESCROW_RELEASE.value,
            )
        )
        return job_cost

    async def get_contract(self, application_id: int, current_user_id: int) -> Optional[JobApplicationInDB]:
        """Fetch a single contract (application) with full details."""
        query = (
            select(JobApplication)
            .where(JobApplication.id == application_id)
            .options(
                selectinload(JobApplication.job).selectinload(Job.employer),
                selectinload(JobApplication.job).selectinload(Job.attachments),
                selectinload(JobApplication.job).selectinload(Job.reviews).selectinload(Review.reviewer),
                selectinload(JobApplication.job).selectinload(Job.reviews).selectinload(Review.reviewee),
                selectinload(JobApplication.worker),
                selectinload(JobApplication.payment),
                selectinload(JobApplication.status_history),
            )
        )
        result = await self.db.execute(query)
        application = result.scalar_one_or_none()

        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contract not found"
            )

        # Check permissions: must be employer or worker
        if application.job.employer_id != current_user_id and application.worker_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this contract"
            )
        
        # Check if the current user has reviewed this job
        application.has_reviewed = any(r.reviewer_id == current_user_id for r in application.job.reviews)

        return application

    async def get_user_contracts(
        self,
        user_id: int,
        role: Optional[str] = None,  # "WORKER" or "EMPLOYER"
        status: Optional[ApplicationStatus] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[JobApplicationInDB]:
        """
        Get contracts for a user (as worker or employer).
        
        Args:
            user_id: Current user ID
            role: Filter by role (WORKER, EMPLOYER)
            status: Filter by application status (PENDING, ACCEPTED, etc.)
            skip, limit: Pagination
        """
        query = select(JobApplication)

        if role == "WORKER":
            query = query.where(JobApplication.worker_id == user_id)
        elif role == "EMPLOYER":
            # Get applications for jobs posted by this employer
            query = query.join(Job).where(Job.employer_id == user_id)
        else:
            # Get contracts where user is either worker or employer
            query = query.where(
                (JobApplication.worker_id == user_id) |
                (JobApplication.job.has(Job.employer_id == user_id))
            )

        if status:
            query = query.where(JobApplication.status == status)

        query = (
            query
            .options(
                selectinload(JobApplication.job).selectinload(Job.employer),
                selectinload(JobApplication.job).selectinload(Job.attachments),
                selectinload(JobApplication.worker),
                selectinload(JobApplication.payment),
                selectinload(JobApplication.status_history),
            )
            .order_by(JobApplication.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(query)
        return result.scalars().unique().all()

    async def get_completed_jobs(
        self,
        user_id: int,
        role: str,  # "WORKER" or "EMPLOYER"
        skip: int = 0,
        limit: int = 20
    ) -> tuple[List[dict], int]:
        """
        Get completed jobs for a user.
        
        Returns:
            Tuple of (completed_jobs_list, total_count)
        """
        base_query = select(JobApplication)

        if role == "WORKER":
            base_query = base_query.where(
                and_(
                    JobApplication.worker_id == user_id,
                    JobApplication.status == ApplicationStatus.ACCEPTED,
                    JobApplication.job.has(Job.status == JobStatus.COMPLETED)
                )
            )
        elif role == "EMPLOYER":
            base_query = base_query.join(Job).where(
                and_(
                    Job.employer_id == user_id,
                    JobApplication.status == ApplicationStatus.ACCEPTED,
                    Job.status == JobStatus.COMPLETED
                )
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role. Must be WORKER or EMPLOYER"
            )

        # Count total
        count_query = select(func.count(JobApplication.id)).select_from(JobApplication)
        
        # Re-apply filters for count query
        if role == "WORKER":
            count_query = count_query.where(
                and_(
                    JobApplication.worker_id == user_id,
                    JobApplication.status == ApplicationStatus.ACCEPTED,
                    JobApplication.job.has(Job.status == JobStatus.COMPLETED)
                )
            )
        elif role == "EMPLOYER":
            count_query = count_query.join(Job).where(
                and_(
                    Job.employer_id == user_id,
                    JobApplication.status == ApplicationStatus.ACCEPTED,
                    Job.status == JobStatus.COMPLETED
                )
            )
        
        count_result = await self.db.execute(count_query)
        total_count = count_result.scalar() or 0

        # Fetch paginated results
        # Ensure Job is joined for ordering (it's already joined for EMPLOYER role)
        if role == "WORKER":
            query = base_query.join(Job)
        else:
            query = base_query
            
        query = (
            query
            .options(
                selectinload(JobApplication.job).selectinload(Job.employer),
                selectinload(JobApplication.worker),
                selectinload(JobApplication.job).selectinload(Job.reviews).selectinload(Review.reviewer),
                selectinload(JobApplication.job).selectinload(Job.reviews).selectinload(Review.reviewee),
                selectinload(JobApplication.job).selectinload(Job.attachments),
                selectinload(JobApplication.payment),
                selectinload(JobApplication.status_history),
            )
            .order_by(Job.completed_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(query)
        applications = result.scalars().unique().all()

        # Transform to response format
        completed_jobs = []
        user_service = UserService(self.db)
        for app in applications:
            # Check if the current user has reviewed this job
            has_reviewed = any(r.reviewer_id == user_id for r in app.job.reviews)

            employer_avatar = await user_service.get_user_avatar_path(app.job.employer_id)
            worker_avatar = await user_service.get_user_avatar_path(app.worker_id)

            job_data = {
                "contract_id": app.id,
                "job_id": app.job_id,
                "job_title": app.job.title,
                "job_description": app.job.description,
                "job_price": app.job.job_price,
                "job_completed_at": app.job.completed_at,
                "employer_id": app.job.employer_id,
                "employer_name": f"{app.job.employer.first_name} {app.job.employer.last_name}" if app.job.employer else "Unknown",
                "employer_avatar": employer_avatar,
                "worker_id": app.worker_id,
                "worker_name": f"{app.worker.first_name} {app.worker.last_name}" if app.worker else "Unknown",
                "worker_avatar": worker_avatar,
                "status": app.status.value if app.status else None,
                "payment_status": app.payment_status.value if app.payment_status else None,
                "review_count": len(app.job.reviews),
                "has_reviewed": has_reviewed,
            }
            completed_jobs.append(job_data)

        return completed_jobs, total_count

    async def get_active_contracts(
        self,
        user_id: int,
        role: str,  # "WORKER" or "EMPLOYER"
        skip: int = 0,
        limit: int = 20
    ) -> List[JobApplicationInDB]:
        """
        Get active (in-progress) contracts for a user.
        """
        base_query = select(JobApplication)

        if role == "WORKER":
            base_query = base_query.where(
                and_(
                    JobApplication.worker_id == user_id,
                    JobApplication.status == ApplicationStatus.ACCEPTED,
                    JobApplication.job.has(Job.status == JobStatus.IN_PROGRESS)
                )
            )
        elif role == "EMPLOYER":
            base_query = base_query.join(Job).where(
                and_(
                    Job.employer_id == user_id,
                    JobApplication.status == ApplicationStatus.ACCEPTED,
                    Job.status == JobStatus.IN_PROGRESS
                )
            )

        query = (
            base_query
            .options(
                selectinload(JobApplication.job).selectinload(Job.employer),
                selectinload(JobApplication.job).selectinload(Job.attachments),
                selectinload(JobApplication.worker),
                selectinload(JobApplication.payment),
                selectinload(JobApplication.status_history),
            )
            .order_by(JobApplication.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(query)
        return result.scalars().unique().all()

    async def activate_contract(
        self,
        application_id: int,
        current_user_id: int,
        started_at: Optional[datetime] = None
    ) -> dict:
        """
        Activate a contract (move job from OPEN to IN_PROGRESS).
        Called when worker starts work.
        
        Args:
            application_id: Application ID
            current_user_id: Current user (must be employer or worker)
            started_at: When work actually started (optional, defaults to now)
        """
        application = await self.get_contract(application_id, current_user_id)

        # Validate application is ACCEPTED
        if application.status != ApplicationStatus.ACCEPTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Contract must be ACCEPTED to activate. Current status: {application.status}"
            )

        # Validate job is OPEN
        if application.job.status != JobStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job must be OPEN to activate. Current status: {application.job.status}"
            )

        # Update job status to IN_PROGRESS
        application.job.status = JobStatus.IN_PROGRESS
        application.job.hired_at = started_at or datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(application.job)

        logger.info(f"Contract activated: application_id={application_id}, job_id={application.job_id}")

        # Notify both parties
        notification_service = NotificationService(self.db)
        
        # Notify employer
        await notification_service.create_notification(
            NotificationCreate(
                user_id=application.job.employer_id,
                title="Work Started",
                message=f"{application.worker.first_name} has started work on '{application.job.title}'",
                category=NotificationCategory.DEADLINES_AND_ACTIONS_REQUIRED,
                action_screen="ContractDetail",
                action_payload={"application_id": application_id}
            )
        )

        # Notify worker
        await notification_service.create_notification(
            NotificationCreate(
                user_id=application.worker_id,
                title="Contract Activated",
                message=f"You've started work on '{application.job.title}'",
                category=NotificationCategory.DEADLINES_AND_ACTIONS_REQUIRED,
                action_screen="ContractDetail",
                action_payload={"application_id": application_id}
            )
        )

        # Emit WebSocket event
        await ws_manager.broadcast_contract_activated(
            contract_id=application_id,
            job_id=application.job_id,
            worker_id=application.worker_id,
            employer_id=application.job.employer_id,
            job_title=application.job.title
        )

        return {
            "success": True,
            "message": "Contract activated successfully",
            "application_id": application_id,
            "job_status": application.job.status.value
        }

    async def mark_complete(
        self,
        application_id: int,
        current_user_id: int
    ) -> dict:
        """
        Mark contract as complete from one party's perspective.
        
        Transition logic:
        - If WORKER marks complete: set Job.worker_completed = True
        - If EMPLOYER marks complete: set Job.employer_completed = True
        - When both marked: Job.status = COMPLETED
        """
        application = await self.get_contract(application_id, current_user_id)

        # Validate application is ACCEPTED
        if application.status != ApplicationStatus.ACCEPTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Contract must be ACCEPTED to mark complete. Current status: {application.status}"
            )

        # Validate job is IN_PROGRESS
        if application.job.status != JobStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job must be IN_PROGRESS to mark complete. Current status: {application.job.status}"
            )

        # Check for disputes
        if application.job.status == JobStatus.DISPUTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot mark job as complete with an open dispute"
            )

        user = await self.db.get(User, current_user_id)
        other_party_id = None

        if user.role == UserRole.WORKER:
            if application.job.worker_completed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You have already marked this job as complete"
                )
            application.job.worker_completed = True
            other_party_id = application.job.employer_id
            marked_by = "worker"

        elif user.role == UserRole.EMPLOYER:
            if application.job.employer_id != current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to mark this job complete"
                )

            if application.job.employer_completed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You have already marked this job as complete"
                )

            application.job.employer_completed = True
            other_party_id = application.worker_id
            marked_by = "employer"

        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only employers and workers can mark jobs complete"
            )

        # Check if both parties have marked complete
        if application.job.worker_completed and application.job.employer_completed:
            payout_amount = await self._release_contract_payment_if_ready(application)
            application.job.status = JobStatus.COMPLETED
            application.job.completed_at = datetime.now(timezone.utc)
            logger.info(f"Contract COMPLETED: application_id={application_id}, job_id={application.job_id}")
            payment_result = await self.db.execute(
                select(Payment).where(Payment.job_id == application.job_id)
            )
            payment = payment_result.scalar_one_or_none()
            if payment:
                payment.status = PaymentStatus.COMPLETED
                payment.completed_at = datetime.now(timezone.utc)
            logger.info(
                f"Contract payout released: application_id={application_id}, amount={payout_amount}"
            )

        await self.db.commit()
        await self.db.refresh(application.job)

        # Notify other party
        notification_service = NotificationService(self.db)
        if marked_by == "worker":
            message = f"{user.first_name} has marked the job '{application.job.title}' as complete. Please review and confirm."
        else:
            message = f"You've marked the job '{application.job.title}' as complete. Awaiting worker confirmation."

        await notification_service.create_notification(
            NotificationCreate(
                user_id=other_party_id,
                title="Job Marked Complete",
                message=message,
                category=NotificationCategory.DEADLINES_AND_ACTIONS_REQUIRED,
                action_screen="ContractDetail",
                action_payload={"application_id": application_id}
            )
        )

        # Emit WebSocket event
        await ws_manager.broadcast_contract_marked_complete(
            contract_id=application_id,
            job_id=application.job_id,
            marked_by_user_id=current_user_id,
            other_party_id=other_party_id,
            marked_by_role=marked_by.upper(),
            job_title=application.job.title
        )

        # If both marked complete, emit completion event
        if application.job.status == JobStatus.COMPLETED:
            await ws_manager.broadcast_contract_completed(
                contract_id=application_id,
                job_id=application.job_id,
                worker_id=application.worker_id,
                employer_id=application.job.employer_id,
                job_title=application.job.title
            )

        return {
            "success": True,
            "message": "Job marked as complete",
            "application_id": application_id,
            "job_status": application.job.status.value,
            "worker_completed": application.job.worker_completed,
            "employer_completed": application.job.employer_completed,
            "completed_at": application.job.completed_at.isoformat() if application.job.completed_at else None
        }

    async def confirm_completion(
        self,
        application_id: int,
        current_user_id: int
    ) -> dict:
        """
        Confirm job completion (if the other party marked complete first).
        This finalizes the job as COMPLETED.
        """
        application = await self.get_contract(application_id, current_user_id)

        # Validate application is ACCEPTED
        if application.status != ApplicationStatus.ACCEPTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contract must be ACCEPTED"
            )

        user = await self.db.get(User, current_user_id)

        # Determine if confirming party is worker or employer
        if user.role == UserRole.WORKER:
            if application.worker_id != current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized"
                )
            if not application.job.employer_completed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Employer has not marked this job complete yet"
                )
            if application.job.worker_completed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You already marked this job complete"
                )
            application.job.worker_completed = True

        elif user.role == UserRole.EMPLOYER:
            if application.job.employer_id != current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized"
                )
            if not application.job.worker_completed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Worker has not marked this job complete yet"
                )
            if application.job.employer_completed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You already marked this job complete"
                )
            application.job.employer_completed = True

        # Both have now marked complete
        payout_amount = await self._release_contract_payment_if_ready(application)
        application.job.status = JobStatus.COMPLETED
        application.job.completed_at = datetime.now(timezone.utc)
        payment_result = await self.db.execute(
            select(Payment).where(Payment.job_id == application.job_id)
        )
        payment = payment_result.scalar_one_or_none()
        if payment:
            payment.status = PaymentStatus.COMPLETED
            payment.completed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(application.job)

        logger.info(
            f"Contract CONFIRMED COMPLETE: application_id={application_id}, job_id={application.job_id}, amount={payout_amount}"
        )

        # Notify both parties
        notification_service = NotificationService(self.db)
        await notification_service.create_notification(
            NotificationCreate(
                user_id=current_user_id,
                title="Job Completion Confirmed",
                message=f"'{application.job.title}' has been completed and closed. You can now leave a review.",
                category=NotificationCategory.DEADLINES_AND_ACTIONS_REQUIRED,
                action_screen="ReviewScreen",
                action_payload={"job_id": application.job_id}
            )
        )

        other_party_id = application.job.employer_id if user.role == UserRole.WORKER else application.worker_id
        await notification_service.create_notification(
            NotificationCreate(
                user_id=other_party_id,
                title="Job Completion Confirmed",
                message=f"'{application.job.title}' has been completed and closed. You can now leave a review.",
                category=NotificationCategory.DEADLINES_AND_ACTIONS_REQUIRED,
                action_screen="ReviewScreen",
                action_payload={"job_id": application.job_id}
            )
        )

        # Emit WebSocket event
        await ws_manager.broadcast_contract_completed(
            contract_id=application_id,
            job_id=application.job_id,
            worker_id=application.worker_id,
            employer_id=application.job.employer_id,
            job_title=application.job.title
        )

        return {
            "success": True,
            "message": "Job completion confirmed",
            "application_id": application_id,
            "job_status": application.job.status.value,
            "completed_at": application.job.completed_at.isoformat()
        }

    async def get_completion_stats(self, user_id: int, role: str) -> dict:
        """Get completion statistics for a user."""
        # Count completed jobs
        completed_query = select(func.count(JobApplication.id)).where(
            and_(
                JobApplication.status == ApplicationStatus.ACCEPTED,
                JobApplication.job.has(Job.status == JobStatus.COMPLETED),
                (JobApplication.worker_id == user_id) if role == "WORKER" else (Job.employer_id == user_id)
            )
        )

        if role == "EMPLOYER":
            completed_query = completed_query.join(Job)

        result = await self.db.execute(completed_query)
        completed_count = result.scalar() or 0

        # Count total jobs (for completion rate)
        total_query = select(func.count(JobApplication.id)).where(
            and_(
                JobApplication.status == ApplicationStatus.ACCEPTED,
                (JobApplication.worker_id == user_id) if role == "WORKER" else (Job.employer_id == user_id)
            )
        )

        if role == "EMPLOYER":
            total_query = total_query.join(Job)

        result = await self.db.execute(total_query)
        total_count = result.scalar() or 0

        completion_rate = (completed_count / total_count * 100) if total_count > 0 else 0.0

        return {
            "completed_jobs": completed_count,
            "total_jobs": total_count,
            "completion_rate": round(completion_rate, 2)
        }
