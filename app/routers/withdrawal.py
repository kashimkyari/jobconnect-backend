from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas
from app.database import get_db
from app.models.user import User
from app.models.enums import WithdrawalRequestStatus
from app.models.dispute import Dispute, DisputeType, DisputeStatus
from app.models.payment import Payment, PaymentStatus
from app.services.auth_service import get_current_user
from app.services.withdrawal_service import WithdrawalService
from app.services.transaction_service import TransactionService
from app.services.tax_withdrawal_service import TaxWithdrawalService
from app.utils.email_service import EmailService
from app.utils.paystack_webhook import PaystackWebhookVerifier
from app.config import settings
from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import json

router = APIRouter(prefix="/withdrawals", tags=["withdrawals"])

logger = logging.getLogger(__name__)


@router.post("/request", response_model=Dict[str, Any])
async def request_withdrawal(
    withdraw_request: schemas.payment.WithdrawalRequestSubmit,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    User submits a withdrawal request.
    Funds are held immediately in pending state.
    Admin must approve for actual transfer to occur.
    
    Request Body:
    - bank_account_id: ID of user's bank account for withdrawal
    - amount: Net amount user wants to receive
    """
    idempotency_key = (
        request.headers.get("X-Request-ID")
        or request.headers.get("Idempotency-Key")
        or request.headers.get("X-Idempotency-Key")
    )
    
    try:
        withdrawal_service = WithdrawalService(db)
        result = await withdrawal_service.request_withdrawal(
            user_id=current_user.id,
            bank_account_id=withdraw_request.bank_account_id,
            amount=Decimal(str(withdraw_request.amount)),
            idempotency_key=idempotency_key,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating withdrawal request for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process withdrawal request"
        )


@router.get("/requests", response_model=List[Dict[str, Any]])
async def get_user_withdrawal_requests(
    status_filter: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get withdrawal requests for the current user.
    Optional status filter: pending, approved, declined, processing, completed, failed
    """
    status_enum = None
    if status_filter:
        try:
            from app.models.enums import WithdrawalRequestStatus
            status_enum = WithdrawalRequestStatus(status_filter.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status filter"
            )
    
    try:
        withdrawal_service = WithdrawalService(db)
        requests = await withdrawal_service.get_user_withdrawal_requests(
            user_id=current_user.id,
            status_filter=status_enum,
            limit=limit,
            offset=offset
        )
        return requests
    except Exception as e:
        logger.error(f"Error fetching withdrawal requests for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch withdrawal requests"
        )


@router.get("/requests/{request_id}", response_model=Dict[str, Any])
async def get_withdrawal_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get details of a specific withdrawal request.
    User can only view their own withdrawal requests.
    """
    try:
        withdrawal_service = WithdrawalService(db)
        request_detail = await withdrawal_service.get_withdrawal_request(request_id)
        
        # Verify user ownership
        if request_detail["user_id"] != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this withdrawal request"
            )
        
        return request_detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching withdrawal request {request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch withdrawal request"
        )


@router.post("/paystack-webhook")
async def paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Paystack webhooks for transfer status updates.
    Triggered when Paystack updates transfer status (success, failed, etc).
    
    Signature verification prevents forged webhook attacks using HMAC-SHA512.
    """
    try:
        # Get raw body and signature for verification
        raw_body = await request.body()
        signature = request.headers.get("X-Paystack-Signature")
        
        # Verify webhook signature
        PaystackWebhookVerifier.verify_and_raise(
            raw_body,
            signature,
            settings.PAYSTACK_WEBHOOK_SECRET,
            webhook_name="Withdrawal transfer webhook"
        )
        
        # Signature verified, parse payload
        payload = json.loads(raw_body)
        logger.info(f"Received verified Paystack transfer webhook: {payload.get('event')}")
        
        event = payload.get("event")
        data = payload.get("data", {})
        
        if event == "transfer.success":
            # Update payment and withdrawal request to COMPLETED
            from sqlalchemy.future import select
            from sqlalchemy import or_
            
            reference = data.get("reference")
            transfer_code = data.get("transfer_code")
            result = await db.execute(
                select(Payment).where(
                    or_(
                        Payment.paystack_reference == reference,
                        Payment.paystack_reference == transfer_code,
                    )
                )
            )
            payment = result.scalar()
            
            if payment and payment.withdrawal_request_id:
                payment.status = PaymentStatus.COMPLETED
                payment.withdrawal_request.status = WithdrawalRequestStatus.COMPLETED
                payment.completed_at = datetime.utcnow()
                await db.commit()
                logger.info(f"Withdrawal payment {payment.id} marked as completed")
                
                # Send completion email
                user = payment.withdrawal_request.user
                bank_account = payment.withdrawal_request.bank_account
                email_service = EmailService()
                await email_service.send_withdrawal_completed(
                    to_email=user.email,
                    user_name=f"{user.first_name} {user.last_name}",
                    withdrawal_amount=TaxWithdrawalService.format_currency(payment.withdrawal_request.amount),
                    total_amount=TaxWithdrawalService.format_currency(payment.withdrawal_request.total_amount),
                    bank_name=bank_account.bank_name,
                    account_number_last_4=bank_account.account_number[-4:],
                    transfer_date=(payment.completed_at or datetime.utcnow()).strftime("%B %d, %Y %H:%M"),
                    dashboard_url=f"{settings.FRONTEND_URL}/wallet",
                    transfer_reference=reference,
                    support_url=f"{settings.FRONTEND_URL}/support"
                )
        
        elif event == "transfer.failed":
            # Update payment and withdrawal request to FAILED
            from sqlalchemy.future import select
            from sqlalchemy import or_
            
            reference = data.get("reference")
            transfer_code = data.get("transfer_code")
            result = await db.execute(
                select(Payment).where(
                    or_(
                        Payment.paystack_reference == reference,
                        Payment.paystack_reference == transfer_code,
                    )
                )
            )
            payment = result.scalar()
            
            if payment and payment.withdrawal_request_id:
                payment.status = PaymentStatus.FAILED
                payment.withdrawal_request.status = WithdrawalRequestStatus.FAILED
                
                # Restore funds to wallet
                payment.withdrawal_request.user.wallet_balance += payment.withdrawal_request.total_amount
                
                # Create automatic dispute for the failed transfer
                failure_reason = data.get("reason", "Transfer failed due to bank issues")
                dispute = Dispute(
                    dispute_type=DisputeType.WITHDRAWAL,
                    withdrawal_request_id=payment.withdrawal_request_id,
                    user_id=payment.withdrawal_request.user_id,
                    reason=f"Paystack transfer failure: {failure_reason}",
                    status=DisputeStatus.OPEN
                )
                db.add(dispute)
                
                await db.commit()
                logger.info(f"Withdrawal payment {payment.id} marked as failed, funds restored, dispute created")
                
                # Send dispute creation email
                user = payment.withdrawal_request.user
                bank_account = payment.withdrawal_request.bank_account
                email_service = EmailService()
                await email_service.send_withdrawal_dispute_created(
                    to_email=user.email,
                    user_name=f"{user.first_name} {user.last_name}",
                    dispute_id=dispute.id,
                    withdrawal_amount=TaxWithdrawalService.format_currency(payment.withdrawal_request.amount),
                    total_amount=TaxWithdrawalService.format_currency(payment.withdrawal_request.total_amount),
                    bank_name=bank_account.bank_name,
                    account_number_last_4=bank_account.account_number[-4:],
                    failure_reason=failure_reason,
                    created_date=dispute.created_at.strftime("%B %d, %Y %H:%M") if dispute.created_at else datetime.utcnow().strftime("%B %d, %Y %H:%M"),
                    dashboard_url=f"{settings.FRONTEND_URL}/wallet",
                    support_url=f"{settings.FRONTEND_URL}/support"
                )
                
                # Send failure email
                await email_service.send_withdrawal_failed(
                    to_email=user.email,
                    user_name=f"{user.first_name} {user.last_name}",
                    withdrawal_amount=TaxWithdrawalService.format_currency(payment.withdrawal_request.amount),
                    total_amount=TaxWithdrawalService.format_currency(payment.withdrawal_request.total_amount),
                    bank_name=bank_account.bank_name,
                    account_number_last_4=bank_account.account_number[-4:],
                    failed_date=(payment.updated_at or datetime.utcnow()).strftime("%B %d, %Y %H:%M"),
                    dashboard_url=f"{settings.FRONTEND_URL}/wallet",
                    transfer_reference=reference,
                    support_url=f"{settings.FRONTEND_URL}/support"
                )
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error processing Paystack webhook: {str(e)}")
        return {"status": "error", "message": str(e)}


@router.post("/withdraw", response_model=schemas.transaction.TransactionInDB)
async def withdraw_funds(
    withdrawal_request: schemas.transaction.WithdrawalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    DEPRECATED: Use POST /withdrawals/request instead.
    
    This endpoint is maintained for backward compatibility.
    Fallback to old withdrawal flow if needed.
    """
    if not current_user.hashed_transaction_pin:
        raise HTTPException(
            status_code=403,
            detail="Transaction PIN not set. Please set up your PIN before making a withdrawal.",
        )

    transaction_service = TransactionService(db)
    transaction = await transaction_service.withdraw_funds(
        user_id=current_user.id,
        amount=withdrawal_request.amount,
        bank_account_id=withdrawal_request.bank_account_id,
        bank_code=withdrawal_request.bank_code,
        account_number=withdrawal_request.account_number,
        bank_name=withdrawal_request.bank_name,
    )
    return transaction
