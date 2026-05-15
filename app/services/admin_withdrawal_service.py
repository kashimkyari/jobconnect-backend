"""
Admin withdrawal management service.
Handles approval, rejection, retry, and monitoring of withdrawal requests.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from sqlalchemy.orm import selectinload
from typing import Optional, Dict, Any
from datetime import datetime

from app.models.withdrawal_request import WithdrawalRequest, WithdrawalRequestStatus
from app.models.user import User
from app.services.admin_audit_service import AdminAuditService
from app.models.admin_audit_log import AdminActionType
from app.utils.email import send_email


class AdminWithdrawalService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit_service = AdminAuditService(db)

    async def get_user_withdrawal_requests(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Get all withdrawal requests for a specific user"""
        query = select(WithdrawalRequest).where(
            WithdrawalRequest.user_id == user_id
        ).order_by(desc(WithdrawalRequest.created_at)).options(
            selectinload(WithdrawalRequest.bank_account),
            selectinload(WithdrawalRequest.user),
        )
        
        total_result = await self.db.execute(
            select(WithdrawalRequest).where(WithdrawalRequest.user_id == user_id)
        )
        total = len(total_result.scalars().all())
        
        result = await self.db.execute(query.offset(skip).limit(limit))
        requests = result.scalars().all()
        
        requests_data = []
        for request in requests:
            requests_data.append({
                "id": request.id,
                "user_id": request.user_id,
                "amount": float(request.amount),
                "tax_amount": float(request.tax_amount),
                "total_amount": float(request.total_amount),
                "tax_preference": request.tax_preference.value if hasattr(request.tax_preference, 'value') else str(request.tax_preference),
                "status": request.status.value if hasattr(request.status, 'value') else str(request.status),
                "bank_account": {
                    "account_number": request.bank_account.account_number if request.bank_account else None,
                    "bank_name": request.bank_account.bank_name if request.bank_account else None,
                    "account_name": request.bank_account.account_name if request.bank_account else None,
                } if request.bank_account else None,
                "admin_notes": request.admin_notes,
                "created_at": request.created_at.isoformat() if request.created_at else None,
                "approved_at": request.approved_at.isoformat() if request.approved_at else None,
            })
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": requests_data,
        }

    async def get_withdrawal_request(self, request_id: int) -> Dict[str, Any]:
        """Get detailed information about a specific withdrawal request"""
        result = await self.db.execute(
            select(WithdrawalRequest).where(
                WithdrawalRequest.id == request_id
            ).options(
                selectinload(WithdrawalRequest.bank_account),
                selectinload(WithdrawalRequest.user),
                selectinload(WithdrawalRequest.approved_by),
            )
        )
        request = result.scalar_one_or_none()
        
        if not request:
            return None
        
        return {
            "id": request.id,
            "user_id": request.user_id,
            "user": {
                "id": request.user.id,
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
                "email": request.user.email,
                "phone": request.user.phone,
            } if request.user else None,
            "amount": float(request.amount),
            "tax_amount": float(request.tax_amount),
            "total_amount": float(request.total_amount),
            "tax_preference": request.tax_preference.value if hasattr(request.tax_preference, 'value') else str(request.tax_preference),
            "status": request.status.value if hasattr(request.status, 'value') else str(request.status),
            "bank_account": {
                "id": request.bank_account.id,
                "account_number": request.bank_account.account_number,
                "bank_name": request.bank_account.bank_name,
                "account_name": request.bank_account.account_name,
                "is_primary": request.bank_account.is_primary,
            } if request.bank_account else None,
            "admin_notes": request.admin_notes,
            "payment_id": request.payment_id,
            "created_at": request.created_at.isoformat() if request.created_at else None,
            "approved_at": request.approved_at.isoformat() if request.approved_at else None,
            "approved_by": {
                "id": request.approved_by.id,
                "first_name": request.approved_by.first_name,
                "last_name": request.approved_by.last_name,
                "email": request.approved_by.email,
            } if request.approved_by else None,
        }

    async def approve_withdrawal(
        self,
        admin_id: int,
        request_id: int,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approve a withdrawal request"""
        result = await self.db.execute(
            select(WithdrawalRequest).where(
                WithdrawalRequest.id == request_id
            ).options(
                selectinload(WithdrawalRequest.user),
            )
        )
        withdrawal_request = result.scalar_one_or_none()
        
        if not withdrawal_request:
            raise ValueError(f"Withdrawal request {request_id} not found")
        
        if withdrawal_request.status != WithdrawalRequestStatus.PENDING:
            raise ValueError(f"Cannot approve withdrawal with status: {withdrawal_request.status}")
        
        old_status = withdrawal_request.status
        withdrawal_request.status = WithdrawalRequestStatus.APPROVED
        withdrawal_request.approved_by_id = admin_id
        withdrawal_request.approved_at = datetime.utcnow()
        withdrawal_request.admin_notes = notes
        
        self.db.add(withdrawal_request)
        await self.db.commit()
        await self.db.refresh(withdrawal_request)
        
        # Log the action
        await self.audit_service.log_action(
            admin_id=admin_id,
            action_type=AdminActionType.WITHDRAWAL_APPROVED,
            target_user_id=withdrawal_request.user_id,
            target_entity_type="withdrawal_request",
            target_entity_id=request_id,
            description=f"Approved withdrawal request ₦{withdrawal_request.amount}",
            old_values={"status": old_status.value if hasattr(old_status, 'value') else str(old_status)},
            new_values={"status": withdrawal_request.status.value if hasattr(withdrawal_request.status, 'value') else str(withdrawal_request.status)},
            context_data={"amount": float(withdrawal_request.amount), "notes": notes},
        )
        
        # Send notification email to user
        try:
            await send_email(
                recipient=withdrawal_request.user.email,
                subject="Withdrawal Request Approved",
                body=f"""
Your withdrawal request of ₦{withdrawal_request.amount} has been approved.
The funds will be transferred to your bank account shortly.
""",
            )
        except Exception as e:
            print(f"Failed to send approval email: {e}")
        
        return {
            "success": True,
            "message": "Withdrawal request approved",
            "request_id": request_id,
            "new_status": "approved",
        }

    async def reject_withdrawal(
        self,
        admin_id: int,
        request_id: int,
        reason: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reject a withdrawal request"""
        result = await self.db.execute(
            select(WithdrawalRequest).where(
                WithdrawalRequest.id == request_id
            ).options(
                selectinload(WithdrawalRequest.user),
            )
        )
        withdrawal_request = result.scalar_one_or_none()
        
        if not withdrawal_request:
            raise ValueError(f"Withdrawal request {request_id} not found")
        
        if withdrawal_request.status != WithdrawalRequestStatus.PENDING:
            raise ValueError(f"Cannot reject withdrawal with status: {withdrawal_request.status}")
        
        old_status = withdrawal_request.status
        withdrawal_request.status = WithdrawalRequestStatus.REJECTED
        withdrawal_request.approved_by_id = admin_id
        withdrawal_request.approved_at = datetime.utcnow()
        withdrawal_request.admin_notes = notes or reason
        
        self.db.add(withdrawal_request)
        await self.db.commit()
        await self.db.refresh(withdrawal_request)
        
        # Reverse the held funds back to user wallet
        user_result = await self.db.execute(select(User).where(User.id == withdrawal_request.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            from decimal import Decimal
            user.wallet_balance = Decimal(str(user.wallet_balance)) + Decimal(str(withdrawal_request.total_amount))
            self.db.add(user)
            await self.db.commit()
        
        # Log the action
        await self.audit_service.log_action(
            admin_id=admin_id,
            action_type=AdminActionType.WITHDRAWAL_REJECTED,
            target_user_id=withdrawal_request.user_id,
            target_entity_type="withdrawal_request",
            target_entity_id=request_id,
            description=f"Rejected withdrawal request ₦{withdrawal_request.amount}. Reason: {reason}",
            old_values={"status": old_status.value if hasattr(old_status, 'value') else str(old_status)},
            new_values={"status": withdrawal_request.status.value if hasattr(withdrawal_request.status, 'value') else str(withdrawal_request.status)},
            context_data={"amount": float(withdrawal_request.amount), "reason": reason, "notes": notes},
        )
        
        # Send notification email to user
        try:
            await send_email(
                recipient=withdrawal_request.user.email,
                subject="Withdrawal Request Rejected",
                body=f"""
Your withdrawal request of ₦{withdrawal_request.amount} has been rejected.
Reason: {reason}

The funds have been credited back to your wallet.
""",
            )
        except Exception as e:
            print(f"Failed to send rejection email: {e}")
        
        return {
            "success": True,
            "message": "Withdrawal request rejected",
            "request_id": request_id,
            "new_status": "rejected",
        }

    async def retry_withdrawal(
        self,
        admin_id: int,
        request_id: int,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retry a failed withdrawal request"""
        result = await self.db.execute(
            select(WithdrawalRequest).where(
                WithdrawalRequest.id == request_id
            ).options(
                selectinload(WithdrawalRequest.user),
            )
        )
        withdrawal_request = result.scalar_one_or_none()
        
        if not withdrawal_request:
            raise ValueError(f"Withdrawal request {request_id} not found")
        
        if withdrawal_request.status != WithdrawalRequestStatus.FAILED:
            raise ValueError(f"Cannot retry withdrawal with status: {withdrawal_request.status}")
        
        old_status = withdrawal_request.status
        withdrawal_request.status = WithdrawalRequestStatus.PENDING
        withdrawal_request.admin_notes = notes
        
        self.db.add(withdrawal_request)
        await self.db.commit()
        await self.db.refresh(withdrawal_request)
        
        # Log the action
        await self.audit_service.log_action(
            admin_id=admin_id,
            action_type=AdminActionType.WITHDRAWAL_RETRIED,
            target_user_id=withdrawal_request.user_id,
            target_entity_type="withdrawal_request",
            target_entity_id=request_id,
            description=f"Retried failed withdrawal request ₦{withdrawal_request.amount}",
            old_values={"status": old_status.value if hasattr(old_status, 'value') else str(old_status)},
            new_values={"status": withdrawal_request.status.value if hasattr(withdrawal_request.status, 'value') else str(withdrawal_request.status)},
            context_data={"amount": float(withdrawal_request.amount), "notes": notes},
        )
        
        return {
            "success": True,
            "message": "Withdrawal request retry initiated",
            "request_id": request_id,
            "new_status": "pending",
        }

    async def add_withdrawal_notes(
        self,
        admin_id: int,
        request_id: int,
        notes: str,
    ) -> Dict[str, Any]:
        """Add or update admin notes on a withdrawal request"""
        result = await self.db.execute(
            select(WithdrawalRequest).where(
                WithdrawalRequest.id == request_id
            )
        )
        withdrawal_request = result.scalar_one_or_none()
        
        if not withdrawal_request:
            raise ValueError(f"Withdrawal request {request_id} not found")
        
        old_notes = withdrawal_request.admin_notes
        withdrawal_request.admin_notes = notes
        
        self.db.add(withdrawal_request)
        await self.db.commit()
        await self.db.refresh(withdrawal_request)
        
        return {
            "success": True,
            "message": "Withdrawal notes updated",
            "request_id": request_id,
            "notes": notes,
        }
