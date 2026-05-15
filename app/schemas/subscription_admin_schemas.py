from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from datetime import datetime


class SubscriptionPlanBase(BaseModel):
    """Base subscription plan schema"""
    name: str = Field(..., min_length=1, description="Unique plan name (e.g., 'freelancer_pro')")
    label: str = Field(..., description="Display name (e.g., 'Freelancer Pro')")
    user_type: str = Field(..., description="'worker' or 'employer'")
    description: Optional[str] = None
    price_monthly: float = Field(..., gt=0, description="Monthly price in NGN")
    price_annually: float = Field(..., gt=0, description="Annual price in NGN")
    currency: str = Field(default="NGN")
    features: Dict = Field(..., description="Features and limits JSON object")
    is_active: bool = Field(default=True)
    is_recommended: bool = Field(default=False)
    sort_order: int = Field(default=0)


class SubscriptionPlanCreate(SubscriptionPlanBase):
    """Create subscription plan"""
    pass


class SubscriptionPlanUpdate(BaseModel):
    """Update subscription plan - all fields optional"""
    name: Optional[str] = None
    label: Optional[str] = None
    user_type: Optional[str] = None
    description: Optional[str] = None
    price_monthly: Optional[float] = None
    price_annually: Optional[float] = None
    currency: Optional[str] = None
    features: Optional[Dict] = None
    is_active: Optional[bool] = None
    is_recommended: Optional[bool] = None
    sort_order: Optional[int] = None


class SubscriptionPlanResponse(SubscriptionPlanBase):
    """Subscription plan response"""
    id: int
    created_at: datetime
    updated_at: datetime
    created_by_admin_id: Optional[int] = None
    
    class Config:
        from_attributes = True


class SubscriptionPlanListResponse(BaseModel):
    """List of subscription plans"""
    status: str = "success"
    data: List[SubscriptionPlanResponse]
    count: int


class SubscriptionPlanDetailResponse(BaseModel):
    """Single subscription plan response"""
    status: str = "success"
    data: SubscriptionPlanResponse
