from pydantic import BaseModel
from datetime import datetime
from app.models.referral import ReferralStatus, RewardStatus
from app.models.user import UserRole


class ReferralBase(BaseModel):
    referrer_id: int
    referred_id: int
    status: ReferralStatus


class ReferralCreate(ReferralBase):
    pass


class ReferralInDB(ReferralBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RewardBase(BaseModel):
    user_id: int
    referral_id: int
    amount: float
    status: RewardStatus


class RewardCreate(RewardBase):
    pass


class RewardInDB(RewardBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReferralSettingsBase(BaseModel):
    user_role: UserRole
    reward_amount: float
    is_active: bool


class ReferralSettingsCreate(ReferralSettingsBase):
    pass


class ReferralSettingsInDB(ReferralSettingsBase):
    id: int

    class Config:
        from_attributes = True
