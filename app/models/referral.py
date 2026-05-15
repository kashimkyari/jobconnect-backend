import enum
from sqlalchemy import Column, Integer, String, Enum, Float, Boolean, DateTime, ForeignKey, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.models.enums import UserRole


class ReferralStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    REWARDED = "rewarded"


class RewardStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, index=True)
    referrer_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    referred_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    status = Column(Enum(ReferralStatus), default=ReferralStatus.PENDING, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now(), nullable=False)

    referrer = relationship("User", foreign_keys=[referrer_id])
    referred = relationship("User", foreign_keys=[referred_id])


class Reward(Base):
    __tablename__ = "rewards"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    referral_id = Column(Integer, ForeignKey("referrals.id"), index=True, nullable=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), index=True, nullable=True)
    reward_type = Column(String, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(Enum(RewardStatus), default=RewardStatus.PENDING, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="rewards")
    referral = relationship("Referral")


class ReferralSettings(Base):
    __tablename__ = "referral_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_role = Column(Enum(UserRole), nullable=False, unique=True)
    reward_amount = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
