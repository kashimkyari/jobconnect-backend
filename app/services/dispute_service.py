from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from typing import List, Optional
from datetime import datetime

from ..models.dispute import Dispute, DisputeStatus
from ..models.dispute_message import DisputeMessage
from ..models.dispute_attachment import DisputeAttachment
from ..models.job import Job, JobStatus
from ..models.user import User, UserRole
from ..models.escrow_transaction import EscrowTransaction, EscrowStatus
from ..models.transaction import Transaction, TransactionType, TransactionStatus
from ..schemas.dispute import DisputeCreate, DisputeUpdate, DisputeMessageCreate
from .notification_service import NotificationService
from ..schemas.notification import NotificationCreate
import uuid
import decimal

class DisputeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        # Note: Depending on the app's structure, we might want to inject other services or
        # instantiate them directly.
        self.notification_service = NotificationService(db)

    async def create_dispute(self, job_id: int, dispute_create: DisputeCreate, user_id: int) -> Dispute:
        job = await self.db.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Job must be in progress or completed to be disputed.
        if job.status not in [JobStatus.IN_PROGRESS, JobStatus.COMPLETED]:
            raise HTTPException(status_code=400, detail="Only in-progress or completed jobs can be disputed")

        if user_id not in [job.employer_id, job.worker_id]:
            raise HTTPException(status_code=403, detail="User not authorized to create dispute for this job")

        # Ensure no active dispute exists
        query = select(Dispute).where(
            Dispute.job_id == job_id, 
            Dispute.status.in_([DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW])
        )
        existing = await self.db.execute(query)
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="An active dispute already exists for this job")

        defendant_id = job.worker_id if user_id == job.employer_id else job.employer_id

        dispute = Dispute(
            job_id=job_id,
            claimant_id=user_id,
            defendant_id=defendant_id,
            reason=dispute_create.reason,
            evidence_url=dispute_create.evidence_url,
            status=DisputeStatus.OPEN
        )
        self.db.add(dispute)
        
        if dispute_create.attachment_urls:
            for url in dispute_create.attachment_urls:
                attachment = DisputeAttachment(
                    dispute=dispute,
                    file_url=url,
                    file_type="video" if url.lower().endswith(('.mp4', '.mov', '.avi', '.webm')) else "image"
                )
                self.db.add(attachment)

        # Freeze escrow if applicable
        escrow_query = select(EscrowTransaction).where(
            EscrowTransaction.job_id == job_id,
            EscrowTransaction.status.in_([EscrowStatus.FUNDED, EscrowStatus.PENDING])
        )
        escrow_result = await self.db.execute(escrow_query)
        escrow = escrow_result.scalar_one_or_none()
        
        if escrow:
            escrow.status = EscrowStatus.DISPUTED
            
        job.dispute_status = "DISPUTED"

        await self.db.commit()
        await self.db.refresh(dispute)
        
        # We optionally notify the defendant via websocket/push here
        # await self.notification_service.create_notification(db=self.db, notification_in=...)
        return dispute

    async def get_dispute_by_id(self, dispute_id: int) -> Optional[Dispute]:
        query = (
            select(Dispute)
            .where(Dispute.id == dispute_id)
            .options(
                selectinload(Dispute.job),
                selectinload(Dispute.claimant),
                selectinload(Dispute.defendant),
                selectinload(Dispute.resolved_by_admin),
                selectinload(Dispute.attachments),
                selectinload(Dispute.messages).selectinload(DisputeMessage.sender),
                selectinload(Dispute.messages).selectinload(DisputeMessage.attachments)
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_disputes_for_user(self, user_id: int) -> List[Dispute]:
        query = (
            select(Dispute)
            .where((Dispute.claimant_id == user_id) | (Dispute.defendant_id == user_id))
            .options(
                selectinload(Dispute.job),
                selectinload(Dispute.claimant),
                selectinload(Dispute.defendant)
            )
            .order_by(Dispute.created_at.desc())
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_disputes_by_job_id(self, job_id: int, user_id: int) -> List[Dispute]:
        job = await self.db.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if user_id not in [job.employer_id, job.worker_id] and not self._is_admin(user_id):
            raise HTTPException(status_code=403, detail="User not authorized to view disputes for this job")

        query = (
            select(Dispute)
            .where(Dispute.job_id == job_id)
            .options(
                selectinload(Dispute.job),
                selectinload(Dispute.messages).selectinload(DisputeMessage.sender)
            )
            .order_by(Dispute.created_at.desc())
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def add_message(self, dispute_id: int, message_in: DisputeMessageCreate, user_id: int) -> DisputeMessage:
        dispute = await self.get_dispute_by_id(dispute_id)
        if not dispute:
            raise HTTPException(status_code=404, detail="Dispute not found")
        
        if dispute.status in [DisputeStatus.RESOLVED, DisputeStatus.REJECTED]:
            raise HTTPException(status_code=400, detail="Cannot add message to a resolved or rejected dispute")
            
        is_admin = False
        if user_id not in [dispute.claimant_id, dispute.defendant_id]:
            if not await self._is_admin(user_id):
                raise HTTPException(status_code=403, detail="Not authorized")
            is_admin = True
            
        new_msg = DisputeMessage(
            dispute_id=dispute_id,
            sender_id=user_id,
            message=message_in.message,
            evidence_url=message_in.evidence_url,
            is_admin_reply=is_admin
        )
        self.db.add(new_msg)

        if message_in.attachment_urls:
            for url in message_in.attachment_urls:
                attachment = DisputeAttachment(
                    message=new_msg,
                    dispute_id=dispute_id,
                    file_url=url,
                    file_type="video" if url.lower().endswith(('.mp4', '.mov', '.avi', '.webm')) else "image"
                )
                self.db.add(attachment)
        await self.db.commit()
        await self.db.refresh(new_msg)
        
        # Eagerly load sender for return
        query = select(DisputeMessage).where(DisputeMessage.id == new_msg.id).options(selectinload(DisputeMessage.sender))
        result = await self.db.execute(query)
        return result.scalar_one()

    async def update_dispute(self, dispute_id: int, dispute_update: DisputeUpdate, admin_id: int) -> Optional[Dispute]:
        dispute = await self.get_dispute_by_id(dispute_id)
        if not dispute:
            return None

        # State transition validation
        if dispute_update.status:
            valid_transition = False
            if dispute.status == DisputeStatus.OPEN and dispute_update.status == DisputeStatus.UNDER_REVIEW:
                valid_transition = True
            elif dispute.status in [DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW] and dispute_update.status in [DisputeStatus.RESOLVED, DisputeStatus.REJECTED]:
                valid_transition = True
                
            if not valid_transition:
                raise HTTPException(status_code=400, detail=f"Invalid transition from {dispute.status} to {dispute_update.status}")
                
            dispute.status = dispute_update.status

        if dispute_update.resolution:
            dispute.resolution = dispute_update.resolution
            dispute.resolved_by_admin_id = admin_id
            dispute.resolved_at = datetime.utcnow()
            
        if dispute_update.status == DisputeStatus.RESOLVED and dispute_update.resolution_action:
            dispute.resolution_action = dispute_update.resolution_action
            await self._process_resolution(dispute, dispute_update.resolution_action)

        await self.db.commit()
        await self.db.refresh(dispute)
        return dispute

    async def _process_resolution(self, dispute: Dispute, action: str):
        job = await self.db.get(Job, dispute.job_id)
        if not job:
            return
            
        escrow_query = select(EscrowTransaction).where(EscrowTransaction.job_id == job.id)
        escrow_result = await self.db.execute(escrow_query)
        escrow = escrow_result.scalar_one_or_none()
        
        # Handle Escrow and Wallet
        if action == "refund":
            if escrow and escrow.status == EscrowStatus.DISPUTED:
                escrow.status = EscrowStatus.REFUNDED
            # Refund Employer
            employer = await self.db.get(User, job.employer_id)
            amount_to_refund = escrow.amount if escrow else decimal.Decimal(str(job.job_price))
            employer.wallet_balance += amount_to_refund
            
            tx = Transaction(
                user_id=employer.id,
                job_id=job.id,
                amount=amount_to_refund,
                status=TransactionStatus.SUCCESS,
                reference=f"REFUND_{job.id}_{uuid.uuid4().hex[:8]}",
                description=f"Refund from dispute resolution for Job #{job.id}",
                transaction_type=TransactionType.REFUND
            )
            self.db.add(tx)
            
        elif action == "release":
            if escrow and escrow.status == EscrowStatus.DISPUTED:
                escrow.status = EscrowStatus.RELEASED
            # Release money to worker
            worker = await self.db.get(User, job.worker_id)
            amount_to_release = escrow.net_amount if escrow else decimal.Decimal(str(job.job_price))
            worker.wallet_balance += amount_to_release
            
            tx = Transaction(
                user_id=worker.id,
                job_id=job.id,
                amount=amount_to_release,
                status=TransactionStatus.SUCCESS,
                reference=f"ESCROW_RELEASE_{job.id}_{uuid.uuid4().hex[:8]}",
                description=f"Fund release from dispute resolution for Job #{job.id}",
                transaction_type=TransactionType.ESCROW_RELEASE
            )
            self.db.add(tx)
            
        job.dispute_status = "RESOLVED"
            
    async def _is_admin(self, user_id: int) -> bool:
        user = await self.db.get(User, user_id)
        return user is not None and user.role == UserRole.ADMIN
