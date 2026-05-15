from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import json
from decimal import Decimal
import logging

from app.models.user import User, UserRole
from app.models.job import Job
from app.models.notification import NotificationCategory
from app.schemas.notification import NotificationCreate
from app.services.notification_service import NotificationService
from app.schemas.transaction import TransactionCreate, InitializePaymentResponse, TransactionInDB
from app.services.payment_service import PaymentService
from app.database import get_db
from app.utils.security import get_current_user, check_permissions
from app.schemas.payment import PaymentInDB
from app.config import settings
from app.utils.paystack_webhook import PaystackWebhookVerifier

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/initialize", response_model=InitializePaymentResponse)
async def initialize_payment(
    payment_data: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Initialize a payment to fund the user's wallet.
    """
    payment_service = PaymentService(db)
    payment_info = await payment_service.initialize_payment(
        user_id=current_user.id,
        amount=payment_data.amount
    )
    return payment_info

@router.post("/callback")
async def payment_callback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Paystack webhook to handle payment verification.
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
            webhook_name="Payment callback webhook"
        )
        
        # Signature verified, parse payload
        payload = json.loads(raw_body)
        event = payload.get("event")
        logger.info(f"Received verified Paystack payment webhook: {event}")
        
        if event == "charge.success":
            reference = payload.get("data", {}).get("reference")
            if reference:
                payment_service = PaymentService(db)
                await payment_service.verify_payment(reference)
                logger.info(f"Payment verified for reference: {reference}")
        
        return {"status": "success"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing payment webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing error"
        )

@router.post("/verify")
async def verify_payment_post(
    reference_data: dict,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify a payment transaction from a POST request.
    """
    reference = reference_data.get("reference")
    if not reference:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reference not provided")
    payment_service = PaymentService(db)
    payment_info = await payment_service.verify_payment(reference)
    return payment_info


@router.get("/verify/{reference}")
async def verify_payment(
    reference: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify a payment transaction.
    """
    payment_service = PaymentService(db)
    payment_info = await payment_service.verify_payment(reference)
    return payment_info
 

@router.post("/pay-worker")
async def pay_worker(
    payment_data: dict,  # { worker_id, amount, pin, otp_code }
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db)
):
    """Transfer funds from employer wallet to worker wallet."""
    payment_service = PaymentService(db)
    
    worker_id = payment_data.get("worker_id")
    amount = payment_data.get("amount")
    pin = payment_data.get("pin")
    otp_code = payment_data.get("otp_code")

    if not all([worker_id, amount, pin]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="worker_id, amount, and pin are required.",
        )

    await payment_service.pay_worker_from_wallet(
        employer_id=current_user.id,
        worker_id=worker_id,
        amount=Decimal(amount),
        pin=pin,
        otp_code=otp_code,
    )
    
    return {"status": "payment successful"}
 

@router.post("/{payment_id}/refund")
async def initiate_refund(
    payment_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db)
):
    payment_service = PaymentService(db)
    # Note: The 10% charge should be handled within the refund logic in payment_service
    refund = await payment_service.initiate_refund(payment_id)
    
    if refund:
        notification_service = NotificationService(db)
        title = "Refund Initiated"
        message = f"A refund of ₦{refund.amount} has been initiated for payment #{refund.id}."

        notifications = [
            NotificationCreate(
                user_id=refund.user_id,
                title=title,
                message=message,
                category=NotificationCategory.PAYMENTS_AND_WALLET,
                action_screen="TransactionHistory",
                action_payload={"payment_id": refund.id}
            )
        ]

        if refund.job_id:
            job = await db.get(Job, refund.job_id)
            if job:
                counterpart_ids = {job.employer_id, job.worker_id}
                counterpart_ids.discard(refund.user_id)
                for uid in counterpart_ids:
                    if uid:
                        notifications.append(
                            NotificationCreate(
                                user_id=uid,
                                title=title,
                                message=message,
                                category=NotificationCategory.PAYMENTS_AND_WALLET,
                                action_screen="JobDetails",
                                action_payload={"job_id": job.id}
                            )
                        )

        for notif in notifications:
            await notification_service.create_notification(notif)

        return {"status": "refund initiated"}

    if refund is None:
        return {"status": "already refunded"}
        
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Could not initiate refund"
    )

@router.post("/withdraw", status_code=status.HTTP_200_OK)
async def withdraw_funds(
    amount: Decimal,
    bank_code: str,
    account_number: str,
    pin: str,
    otp_code: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Withdraw funds from user's wallet.
    """
    payment_service = PaymentService(db)
    bank_details = {"bank_code": bank_code, "account_number": account_number}
    await payment_service.withdraw_funds(
        user_id=current_user.id,
        amount=amount,
        bank_details=bank_details,
        pin=pin,
        otp_code=otp_code
    )
    return {"status": "withdrawal successful"}

@router.get("/history", response_model=List[PaymentInDB])
async def get_payment_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the payment history for the currently authenticated user.
    """
    payment_service = PaymentService(db)
    payments = await payment_service.get_user_payments(user_id=current_user.id)
    return payments

@router.get("/transactions", response_model=List[TransactionInDB])
async def get_transactions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the transaction history for the currently authenticated user.
    """
    payment_service = PaymentService(db)
    transactions = await payment_service.get_user_transactions(user_id=current_user.id)
    return transactions

@router.get("/banks")
async def get_banks(
    db: AsyncSession = Depends(get_db)
):
    """
    Get a list of supported banks.
    """
    payment_service = PaymentService(db)
    banks = await payment_service.get_banks()
    return banks

@router.post("/resolve-account")
async def resolve_account(
    account_number: str,
    bank_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Resolve a bank account to get the account name.
    """
    payment_service = PaymentService(db)
    account_details = await payment_service.resolve_account(account_number, bank_code)
    return account_details

@router.get("/banks")
async def get_banks(
    db: AsyncSession = Depends(get_db)
):
    """
    Get a list of supported banks.
    """
    payment_service = PaymentService(db)
    banks = await payment_service.get_banks()
    return banks

@router.post("/resolve-account")
async def resolve_account(
    account_number: str,
    bank_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Resolve a bank account to get the account name.
    """
    payment_service = PaymentService(db)
    account_details = await payment_service.resolve_account(account_number, bank_code)
    return account_details

@router.post("/pay-worker")
async def pay_worker(
    payment_data: dict,  # { worker_id, amount, pin, otp_code }
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER)),
    db: AsyncSession = Depends(get_db)
):
    """Transfer funds from employer wallet to worker wallet."""
    payment_service = PaymentService(db)
    
    # Verify transaction PIN
    # Verify OTP if 2FA enabled
    # Process transfer
    # Return confirmation
    
    return await payment_service.transfer_to_worker(
        from_user_id=current_user.id,
        to_user_id=payment_data['worker_id'],
        amount=payment_data['amount'],
        transaction_pin=payment_data['pin']
    )
