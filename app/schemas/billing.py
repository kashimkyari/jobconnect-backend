from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from .payment import PaymentType, PaymentStatus

class WalletTransaction(BaseModel):
    """Wallet transaction history item"""
    id: int
    user_id: int
    amount: float
    payment_type: PaymentType
    status: PaymentStatus
    description: str
    created_at: datetime

    class Config:
        from_attributes = True

class SubscriptionStatus(BaseModel):
    """User's subscription status"""
    is_active: bool
    expiry_date: Optional[datetime]
    days_remaining: Optional[int]
    in_grace_period: bool

class SubscriptionResponse(BaseModel):
    """Response for subscription initiation"""
    subscription_id: int
    authorization_url: str
    reference: str
    status: str
