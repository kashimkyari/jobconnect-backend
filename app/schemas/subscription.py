from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class SubscriptionPlanBase(BaseModel):
    name: str = Field(..., min_length=3)
    price_monthly: float = Field(..., ge=0)
    price_annually: float = Field(..., ge=0)
    features: Dict[str, Any]

class SubscriptionPlanCreate(SubscriptionPlanBase):
    pass

class SubscriptionPlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3)
    price_monthly: Optional[float] = Field(None, ge=0)
    price_annually: Optional[float] = Field(None, ge=0)
    features: Optional[Dict[str, Any]] = None

class SubscriptionPlanInDB(SubscriptionPlanBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class SubscriptionCreate(BaseModel):
    plan_id: int
    billing_cycle: str

class SubscriptionInDB(SubscriptionPlanInDB):
    pass

class UserSubscriptionResponse(BaseModel):
    """Response for active user subscription with metadata"""
    plan: SubscriptionPlanInDB
    subscription_status: bool
    subscription_expiry: Optional[datetime]
    days_remaining: int = 0
    is_refundable: bool = False  # True if within 3 days

    class Config:
        from_attributes = True
