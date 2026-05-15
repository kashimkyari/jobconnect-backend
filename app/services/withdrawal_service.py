"""
Service for handling withdrawal request workflows with admin approval.
Includes fund holding, approval/decline, and Paystack transfer coordination.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, desc
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime
import httpx
import logging

from app.models.withdrawal_request import WithdrawalRequest
from app.models.payment import Payment, PaymentStatus, PaymentType
from app.models.user import User
from app.models.bank_account import BankAccount
from app.models.enums import WithdrawalRequestStatus, TaxPreference
from app.schemas.notification import NotificationCreate
from app.models.notification import NotificationCategory
from app.config import settings
from app.services.notification_service import NotificationService
from app.utils.logging import payment_logger
from app.utils.email_service import EmailService

logger = logging.getLogger(__name__)


class WithdrawalService:
    """Service for managing withdrawal requests and approvals"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        if not settings.PAYSTACK_SECRET_KEY:
            raise ValueError("PAYSTACK_SECRET_KEY is not set")
        self.base_url = settings.PAYSTACK_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }

    @staticmethod
    def _extract_paystack_error(response: httpx.Response) -> Dict[str, Any]:
        """Normalize Paystack error payload for client-safe messaging."""
        try:
            payload = response.json() if response.content else {}
        except Exception:
            payload = {}
        meta = payload.get("meta") or {}
        return {
            "status_code": response.status_code,
            "message": payload.get("message") or response.text or "Paystack request failed",
            "code": payload.get("code"),
            "next_step": meta.get("nextStep"),
            "type": payload.get("type"),
        }
    
    async def request_withdrawal(
        self,
        user_id: int,
        bank_account_id: int,
        amount: Decimal,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a withdrawal request and hold funds immediately.
        
        Args:
            user_id: User making the request
            bank_account_id: Target bank account for withdrawal
            amount: Amount to withdraw (net amount user wants to receive)
        
        Returns:
            Dict with withdrawal request details
        """
        # Validate user
        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Validate bank account ownership
        bank_account = await self.db.get(BankAccount, bank_account_id)
        if not bank_account or bank_account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bank account not found or doesn't belong to user"
            )
        
        # Tax has been removed from withdrawals: user is charged exactly requested amount.
        tax_preference = TaxPreference.BEFORE
        tax_amount = Decimal("0.00")
        charge_amount = Decimal(str(amount))
        
        # Best-effort idempotency guard for client retries.
        # If a matching pending request exists recently, return it instead of charging wallet twice.
        if idempotency_key:
            recent_cutoff = datetime.utcnow().timestamp() - (10 * 60)
            existing_result = await self.db.execute(
                select(WithdrawalRequest).where(
                    and_(
                        WithdrawalRequest.user_id == user_id,
                        WithdrawalRequest.bank_account_id == bank_account_id,
                        WithdrawalRequest.amount == Decimal(str(amount)),
                        WithdrawalRequest.status == WithdrawalRequestStatus.PENDING,
                    )
                ).order_by(desc(WithdrawalRequest.created_at)).limit(1)
            )
            existing_request = existing_result.scalar_one_or_none()
            if (
                existing_request
                and existing_request.created_at
                and existing_request.created_at.timestamp() >= recent_cutoff
            ):
                return {
                    "id": existing_request.id,
                    "amount": float(existing_request.amount),
                    "tax_amount": float(existing_request.tax_amount),
                    "total_amount": float(existing_request.total_amount),
                    "tax_preference": existing_request.tax_preference.value,
                    "status": existing_request.status.value,
                    "bank_account": {
                        "account_name": bank_account.account_name,
                        "account_number": bank_account.account_number,
                        "bank_name": bank_account.bank_name,
                    },
                    "created_at": existing_request.created_at.isoformat(),
                }
        
        # Validate sufficient balance (no tax markup).
        if user.wallet_balance < charge_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient wallet balance. Available: {user.wallet_balance}, Required: {charge_amount}",
            )
        
        # Create withdrawal request
        try:
            withdrawal_request = WithdrawalRequest(
                user_id=user_id,
                bank_account_id=bank_account_id,
                amount=Decimal(str(amount)),
                tax_amount=tax_amount,
                tax_preference=tax_preference,
                total_amount=charge_amount,
                status=WithdrawalRequestStatus.PENDING
            )
            self.db.add(withdrawal_request)
            await self.db.flush()  # Get the ID without committing
            
            # Deduct funds from wallet immediately (hold them)
            user.wallet_balance -= charge_amount
            
            await self.db.commit()
            
            payment_logger.info(
                "Withdrawal request created",
                user_id=user_id,
                withdrawal_request_id=withdrawal_request.id,
                amount=str(amount),
                tax_amount=str(tax_amount),
                charge_amount=str(charge_amount)
            )
            
            # Send notification to user
            notification_service = NotificationService(self.db)
            await notification_service.create_notification(NotificationCreate(
                user_id=user_id,
                title="Withdrawal Request Submitted",
                message=f"Your withdrawal request of {amount} NGN has been submitted for admin approval.",
                category=NotificationCategory.PAYMENTS_AND_WALLET,
                action_screen="WithdrawalRequests",
                action_payload={"withdrawal_request_id": withdrawal_request.id}
            ))
            
            # Send email notification
            email_service = EmailService()
            await email_service.send_withdrawal_request_submitted(
                to_email=user.email,
                user_name=f"{user.first_name} {user.last_name}",
                withdrawal_amount=f"NGN {withdrawal_request.amount:,.2f}",
                tax_amount=f"NGN {tax_amount:,.2f}",
                total_amount=f"NGN {charge_amount:,.2f}",
                tax_rate="0%",
                bank_name=bank_account.bank_name,
                account_number_last_4=bank_account.account_number[-4:],
                request_date=withdrawal_request.created_at.strftime("%B %d, %Y %H:%M"),
                dashboard_url=f"{settings.FRONTEND_URL}/wallet"
            )
            
            return {
                "id": withdrawal_request.id,
                "amount": float(withdrawal_request.amount),
                "tax_amount": float(withdrawal_request.tax_amount),
                "total_amount": float(withdrawal_request.total_amount),
                "tax_preference": withdrawal_request.tax_preference.value,
                "status": withdrawal_request.status.value,
                "bank_account": {
                    "account_name": bank_account.account_name,
                    "account_number": bank_account.account_number,
                    "bank_name": bank_account.bank_name
                },
                "created_at": withdrawal_request.created_at.isoformat()
            }
            
        except Exception as e:
            await self.db.rollback()
            payment_logger.error(
                "Failed to create withdrawal request",
                user_id=user_id,
                error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process withdrawal request"
            )
    
    async def get_user_withdrawal_requests(
        self,
        user_id: int,
        status_filter: Optional[WithdrawalRequestStatus] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get withdrawal requests for a user"""
        query = select(WithdrawalRequest).where(WithdrawalRequest.user_id == user_id)
        query = query.options(
            selectinload(WithdrawalRequest.bank_account),
            selectinload(WithdrawalRequest.approved_by),
        )
        
        if status_filter:
            query = query.where(WithdrawalRequest.status == status_filter)
        
        query = query.order_by(desc(WithdrawalRequest.created_at)).limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        requests = result.scalars().all()
        
        return [
            {
                "id": req.id,
                "amount": float(req.amount),
                "tax_amount": float(req.tax_amount),
                "total_amount": float(req.total_amount),
                "tax_preference": req.tax_preference.value,
                "status": req.status.value,
                "bank_account": {
                    "account_name": req.bank_account.account_name,
                    "account_number": req.bank_account.account_number,
                    "bank_name": req.bank_account.bank_name
                },
                "created_at": req.created_at.isoformat(),
                "approved_at": req.approved_at.isoformat() if req.approved_at else None,
                "admin_notes": req.admin_notes
            }
            for req in requests
        ]
    
    async def get_withdrawal_request(self, request_id: int) -> Dict[str, Any]:
        """Get details of a specific withdrawal request"""
        request_result = await self.db.execute(
            select(WithdrawalRequest).options(
                selectinload(WithdrawalRequest.user),
                selectinload(WithdrawalRequest.bank_account),
                selectinload(WithdrawalRequest.approved_by),
            ).where(WithdrawalRequest.id == request_id).limit(1)
        )
        request = request_result.scalar_one_or_none()
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Withdrawal request not found"
            )
        
        return {
            "id": request.id,
            "user_id": request.user_id,
            "user": {
                "id": request.user.id,
                "email": request.user.email,
                "first_name": request.user.first_name,
                "last_name": request.user.last_name
            },
            "amount": float(request.amount),
            "tax_amount": float(request.tax_amount),
            "total_amount": float(request.total_amount),
            "tax_preference": request.tax_preference.value,
            "status": request.status.value,
            "bank_account": {
                "account_name": request.bank_account.account_name,
                "account_number": request.bank_account.account_number,
                "bank_name": request.bank_account.bank_name,
                "bank_code": request.bank_account.bank_code
            },
            "created_at": request.created_at.isoformat(),
            "approved_at": request.approved_at.isoformat() if request.approved_at else None,
            "approved_by": {
                "id": request.approved_by.id,
                "email": request.approved_by.email
            } if request.approved_by else None,
            "admin_notes": request.admin_notes
        }
    
    async def approve_withdrawal_request(
        self,
        request_id: int,
        admin_id: int,
        notes: str = None
    ) -> Dict[str, Any]:
        """
        Admin approves a withdrawal request and initiates Paystack transfer.
        
        Args:
            request_id: Withdrawal request to approve
            admin_id: ID of admin approving
            notes: Optional notes from admin
        
        Returns:
            Dict with payment details after Paystack transfer initiation
        """
        # Verify admin user
        admin_user = await self.db.get(User, admin_id)
        if not admin_user or admin_user.role.value != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can approve withdrawals"
            )
        
        # Get withdrawal request with all required relationships eager-loaded
        # to avoid async lazy-loading (greenlet_spawn errors).
        withdrawal_result = await self.db.execute(
            select(WithdrawalRequest).options(
                selectinload(WithdrawalRequest.user),
                selectinload(WithdrawalRequest.bank_account),
                selectinload(WithdrawalRequest.payment),
            ).where(WithdrawalRequest.id == request_id).limit(1)
        )
        withdrawal_request = withdrawal_result.scalar_one_or_none()
        if not withdrawal_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Withdrawal request not found"
            )

        if withdrawal_request.payment_id and withdrawal_request.payment:
            payment = withdrawal_request.payment
            transfer_reference = payment.paystack_reference
            transfer_code = payment.payment_metadata.get("transfer_code") if payment.payment_metadata else None
            return {
                "withdrawal_request_id": withdrawal_request.id,
                "payment_id": payment.id,
                "amount": float(withdrawal_request.amount),
                "transfer_reference": transfer_reference,
                "transfer_code": transfer_code,
                "status": withdrawal_request.status.value,
                "approved_at": withdrawal_request.approved_at.isoformat() if withdrawal_request.approved_at else None,
            }
        
        if withdrawal_request.status in {
            WithdrawalRequestStatus.APPROVED,
            WithdrawalRequestStatus.PROCESSING,
            WithdrawalRequestStatus.COMPLETED,
        }:
            # Idempotency: repeated approve should return the already-approved result.
            payment = withdrawal_request.payment
            transfer_reference = payment.paystack_reference if payment else None
            transfer_code = payment.payment_metadata.get("transfer_code") if payment and payment.payment_metadata else None
            return {
                "withdrawal_request_id": withdrawal_request.id,
                "payment_id": payment.id if payment else None,
                "amount": float(withdrawal_request.amount),
                "transfer_reference": transfer_reference,
                "transfer_code": transfer_code,
                "status": withdrawal_request.status.value,
                "approved_at": withdrawal_request.approved_at.isoformat() if withdrawal_request.approved_at else None,
            }
        
        if withdrawal_request.status != WithdrawalRequestStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot approve request in {withdrawal_request.status.value} status"
            )
        
        try:
            bank_account = withdrawal_request.bank_account
            user = withdrawal_request.user
            transfer_reference = f"withdrawal-{withdrawal_request.id}"
            transfer_data = await self._initiate_paystack_transfer(
                withdrawal_request=withdrawal_request,
                transfer_reference=transfer_reference,
            )

            existing_payment_result = await self.db.execute(
                select(Payment).where(Payment.paystack_reference == transfer_data["transfer_reference"]).limit(1)
            )
            existing_payment = existing_payment_result.scalar_one_or_none()
            if existing_payment:
                withdrawal_request.status = WithdrawalRequestStatus.APPROVED
                withdrawal_request.approved_by_id = admin_id
                withdrawal_request.approved_at = withdrawal_request.approved_at or datetime.utcnow()
                withdrawal_request.admin_notes = notes
                withdrawal_request.payment_id = existing_payment.id
                await self.db.commit()
                return {
                    "withdrawal_request_id": withdrawal_request.id,
                    "payment_id": existing_payment.id,
                    "amount": float(withdrawal_request.amount),
                    "transfer_reference": transfer_data["transfer_reference"],
                    "transfer_code": transfer_data["transfer_code"],
                    "status": withdrawal_request.status.value,
                    "approved_at": withdrawal_request.approved_at.isoformat() if withdrawal_request.approved_at else None,
                }

            # Create Payment record linked to withdrawal request
            payment = Payment(
                user_id=withdrawal_request.user_id,
                withdrawal_request_id=withdrawal_request.id,
                amount=withdrawal_request.amount,
                payment_type=PaymentType.WITHDRAWAL,
                status=PaymentStatus.PROCESSING,
                paystack_reference=transfer_data["transfer_reference"],
                description=f"Withdrawal from bank account ending in {bank_account.account_number[-4:]}",
                payment_metadata={
                    "transfer_code": transfer_data["transfer_code"],
                    "recipient_code": transfer_data.get("recipient_code"),
                    "transfer_id": transfer_data.get("transfer_id"),
                },
            )
            self.db.add(payment)
            await self.db.flush()  # Flush to get the payment ID
            
            # Update withdrawal request status
            withdrawal_request.status = WithdrawalRequestStatus.APPROVED
            withdrawal_request.approved_by_id = admin_id
            withdrawal_request.approved_at = datetime.utcnow()
            withdrawal_request.admin_notes = notes
            withdrawal_request.payment_id = payment.id
            
            await self.db.commit()
            
            payment_logger.info(
                "Withdrawal request approved",
                withdrawal_request_id=request_id,
                admin_id=admin_id,
                transfer_code=transfer_data["transfer_code"],
                transfer_reference=transfer_data["transfer_reference"],
            )
            
            # Send notification to user
            notification_service = NotificationService(self.db)
            await notification_service.create_notification(NotificationCreate(
                user_id=withdrawal_request.user_id,
                title="Withdrawal Approved",
                message=f"Your withdrawal of {withdrawal_request.amount} NGN has been approved and is being transferred to your bank account.",
                category=NotificationCategory.PAYMENTS_AND_WALLET,
                action_screen="WithdrawalRequests",
                action_payload={"withdrawal_request_id": withdrawal_request.id}
            ))
            
            # Send email notification
            email_service = EmailService()
            await email_service.send_withdrawal_approved(
                to_email=user.email,
                user_name=f"{user.first_name} {user.last_name}",
                withdrawal_amount=f"NGN {withdrawal_request.amount:,.2f}",
                tax_amount=f"NGN {withdrawal_request.tax_amount:,.2f}",
                total_amount=f"NGN {withdrawal_request.total_amount:,.2f}",
                bank_name=bank_account.bank_name,
                account_number_last_4=bank_account.account_number[-4:],
                approved_date=withdrawal_request.approved_at.strftime("%B %d, %Y %H:%M"),
                dashboard_url=f"{settings.FRONTEND_URL}/wallet",
                transfer_reference=transfer_data["transfer_reference"],
                admin_notes=notes
            )
            
            return {
                "withdrawal_request_id": withdrawal_request.id,
                "payment_id": payment.id,
                "amount": float(withdrawal_request.amount),
                "transfer_reference": transfer_data["transfer_reference"],
                "transfer_code": transfer_data["transfer_code"],
                "status": withdrawal_request.status.value,
                "approved_at": withdrawal_request.approved_at.isoformat()
            }
            
        except httpx.HTTPStatusError as e:
            await self.db.rollback()
            payment_logger.error(
                "Paystack transfer failed",
                request_id=request_id,
                status_code=e.response.status_code,
                error=e.response.text
            )
            error_data = self._extract_paystack_error(e.response)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": error_data["message"],
                    "code": error_data["code"],
                    "next_step": error_data["next_step"],
                    "provider": "paystack",
                }
            )
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            payment_logger.error(
                "Withdrawal approval failed",
                request_id=request_id,
                error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to approve withdrawal"
            )
    
    async def decline_withdrawal_request(
        self,
        request_id: int,
        admin_id: int,
        reason: str
    ) -> Dict[str, Any]:
        """
        Admin declines a withdrawal request and restores funds to wallet.
        
        Args:
            request_id: Withdrawal request to decline
            admin_id: ID of admin declining
            reason: Reason for decline
        
        Returns:
            Dict with decline confirmation details
        """
        # Verify admin
        admin_user = await self.db.get(User, admin_id)
        if not admin_user or admin_user.role.value != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can decline withdrawals"
            )
        
        # Get withdrawal request with user/bank loaded up-front to avoid
        # lazy-loading IO from relationship access in async context.
        withdrawal_result = await self.db.execute(
            select(WithdrawalRequest).options(
                selectinload(WithdrawalRequest.user),
                selectinload(WithdrawalRequest.bank_account),
            ).where(WithdrawalRequest.id == request_id).limit(1)
        )
        withdrawal_request = withdrawal_result.scalar_one_or_none()
        if not withdrawal_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Withdrawal request not found"
            )
        
        if withdrawal_request.status == WithdrawalRequestStatus.DECLINED:
            # Idempotency: repeated decline returns same terminal response.
            return {
                "withdrawal_request_id": withdrawal_request.id,
                "status": withdrawal_request.status.value,
                "amount_restored": 0.0,
                "reason": withdrawal_request.admin_notes or reason,
                "declined_at": withdrawal_request.approved_at.isoformat() if withdrawal_request.approved_at else None,
            }
        
        if withdrawal_request.status != WithdrawalRequestStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot decline request in {withdrawal_request.status.value} status"
            )
        
        try:
            # Restore funds to wallet
            user = withdrawal_request.user
            bank_account = withdrawal_request.bank_account
            user.wallet_balance += withdrawal_request.total_amount
            
            # Update withdrawal request
            withdrawal_request.status = WithdrawalRequestStatus.DECLINED
            withdrawal_request.approved_by_id = admin_id
            withdrawal_request.approved_at = datetime.utcnow()
            withdrawal_request.admin_notes = reason
            
            await self.db.commit()
            
            payment_logger.info(
                "Withdrawal request declined",
                request_id=request_id,
                admin_id=admin_id,
                reason=reason
            )
            
            # Send notification to user
            notification_service = NotificationService(self.db)
            await notification_service.create_notification(NotificationCreate(
                user_id=withdrawal_request.user_id,
                title="Withdrawal Declined",
                message=f"Your withdrawal request of {withdrawal_request.amount} NGN has been declined. Reason: {reason}. Funds have been restored to your wallet.",
                category=NotificationCategory.PAYMENTS_AND_WALLET,
                action_screen="WithdrawalRequests",
                action_payload={"withdrawal_request_id": withdrawal_request.id}
            ))
            
            # Send email notification
            email_service = EmailService()
            await email_service.send_withdrawal_declined(
                to_email=user.email,
                user_name=f"{user.first_name} {user.last_name}",
                withdrawal_amount=f"NGN {withdrawal_request.amount:,.2f}",
                total_amount=f"NGN {withdrawal_request.total_amount:,.2f}",
                bank_name=bank_account.bank_name,
                account_number_last_4=bank_account.account_number[-4:],
                declined_date=withdrawal_request.approved_at.strftime("%B %d, %Y %H:%M"),
                dashboard_url=f"{settings.FRONTEND_URL}/wallet",
                decline_reason=reason,
                support_url=f"{settings.FRONTEND_URL}/support",
                faq_url=f"{settings.FRONTEND_URL}/help/withdrawals"
            )
            
            return {
                "withdrawal_request_id": withdrawal_request.id,
                "status": withdrawal_request.status.value,
                "amount_restored": float(withdrawal_request.total_amount),
                "reason": reason,
                "declined_at": withdrawal_request.approved_at.isoformat()
            }
            
        except Exception as e:
            await self.db.rollback()
            payment_logger.error(
                "Withdrawal decline failed",
                request_id=request_id,
                error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to decline withdrawal"
            )

    async def _initiate_paystack_transfer(
        self,
        withdrawal_request: WithdrawalRequest,
        transfer_reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Internal method to initiate a Paystack transfer for a withdrawal request.
        Reusable for both initial approvals and dispute retries.
        
        Args:
            withdrawal_request: The withdrawal request to process
        
        Returns:
            Dict with transfer_code and recipient_code
        
        Raises:
            HTTPException on Paystack API failure
        """
        try:
            bank_account = withdrawal_request.bank_account
            recipient_code = bank_account.recipient_code

            if not recipient_code:
                # Create transfer recipient with bank details once and reuse.
                recipient_payload = {
                    "type": "nuban",
                    "name": bank_account.account_name,
                    "account_number": bank_account.account_number,
                    "bank_code": bank_account.bank_code,
                    "currency": "NGN"
                }
                
                async with httpx.AsyncClient(timeout=30) as client:
                    recipient_response = await client.post(
                        f"{self.base_url}/transferrecipient",
                        headers=self.headers,
                        json=recipient_payload
                    )
                    recipient_response.raise_for_status()
                    recipient_data = recipient_response.json()
                
                recipient_code = recipient_data['data']['recipient_code']
                bank_account.recipient_code = recipient_code
            
            # Initiate Paystack transfer
            transfer_amount_kobo = int(float(withdrawal_request.amount) * 100)  # Convert to kobo
            transfer_payload = {
                "source": "balance",
                "amount": transfer_amount_kobo,
                "recipient": recipient_code,
                "reason": f"JobConnect Withdrawal - Request #{withdrawal_request.id}",
            }
            if transfer_reference:
                transfer_payload["reference"] = transfer_reference
            
            async with httpx.AsyncClient(timeout=30) as client:
                transfer_response = await client.post(
                    f"{self.base_url}/transfer",
                    headers=self.headers,
                    json=transfer_payload
                )

                # Idempotency-safe fallback: Paystack can reject duplicate references.
                if transfer_response.status_code >= 400 and transfer_reference:
                    body = transfer_response.json() if transfer_response.content else {}
                    message = str(body.get("message", "")).lower()
                    if "duplicate" in message and "reference" in message:
                        verify_response = await client.get(
                            f"{self.base_url}/transfer/verify/{transfer_reference}",
                            headers=self.headers,
                        )
                        verify_response.raise_for_status()
                        transfer_data = verify_response.json()
                    else:
                        transfer_response.raise_for_status()
                        transfer_data = transfer_response.json()
                else:
                    transfer_response.raise_for_status()
                    transfer_data = transfer_response.json()
            
            return {
                "transfer_code": transfer_data["data"]["transfer_code"],
                "transfer_reference": transfer_data["data"].get("reference", transfer_reference),
                "recipient_code": recipient_code,
                "transfer_id": transfer_data["data"].get("id"),
            }
        
        except httpx.HTTPStatusError as e:
            error_data = self._extract_paystack_error(e.response)
            payment_logger.error(
                "Paystack transfer failed",
                withdrawal_request_id=withdrawal_request.id,
                status_code=e.response.status_code,
                error=e.response.text
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": error_data["message"],
                    "code": error_data["code"],
                    "next_step": error_data["next_step"],
                    "provider": "paystack",
                }
            )
        except Exception as e:
            payment_logger.error(
                "Transfer initiation error",
                withdrawal_request_id=withdrawal_request.id,
                error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process transfer"
            )
