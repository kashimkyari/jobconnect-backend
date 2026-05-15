from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from ..models.user import User
from ..services.auth_service import get_current_user, get_admin_user
from ..schemas.admin import WalletFundingRequest, PaystackWebhookData
from ..schemas.payment import PaymentResponse
from ..schemas.billing import SubscriptionResponse
from ..services.admin_service import AdminService
from ..database import get_db

router = APIRouter(prefix="/revenue", tags=["revenue"])

# Employer Subscription Endpoints
@router.post("/subscription", response_model=SubscriptionResponse)
async def create_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    admin_service = AdminService(db)
    return await admin_service.initiate_subscription(current_user)

@router.post("/subscription/webhook")
async def subscription_webhook(
    data: PaystackWebhookData,
    db: Session = Depends(get_db)
):
    admin_service = AdminService(db)
    await admin_service.process_subscription_webhook(data.dict())
    return {"status": "success"}

# Worker Wallet Endpoints
@router.post("/wallet/fund", response_model=PaymentResponse)
async def fund_wallet(
    data: WalletFundingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    admin_service = AdminService(db)
    return await admin_service.fund_wallet(current_user, data.amount)

@router.post("/wallet/webhook")
async def wallet_webhook(
    data: PaystackWebhookData,
    db: Session = Depends(get_db)
):
    admin_service = AdminService(db)
    await admin_service.process_wallet_webhook(data.dict())
    return {"status": "success"}

# Admin Revenue Management Endpoints
@router.get("/subscriptions", response_model=List[SubscriptionResponse])
async def get_active_subscriptions(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    admin_service = AdminService(db)
    return await admin_service.get_active_subscriptions()

@router.get("/escrow", response_model=List[PaymentResponse])
async def get_escrow_transactions(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    admin_service = AdminService(db)
    return await admin_service.get_escrow_transactions()

@router.post("/escrow/{transaction_id}/release")
async def release_escrow(
    transaction_id: int,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    admin_service = AdminService(db)
    await admin_service.release_escrow(transaction_id)
    return {"status": "success"}
