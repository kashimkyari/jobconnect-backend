from sqlalchemy import Column, Integer, String, Float, JSON, Boolean, DateTime as SQLDateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime
from enum import Enum as PyEnum

from app.db.base_class import Base


class UserTypeEnum(PyEnum):
    """User type enumeration"""
    WORKER = "worker"
    EMPLOYER = "employer"


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    label = Column(String, nullable=False)  # Display name (e.g., "Freelancer Pro")
    user_type = Column(String, nullable=False, index=True)  # "worker" or "employer"
    description = Column(String, nullable=True)
    price_monthly = Column(Float, nullable=False)
    price_annually = Column(Float, nullable=False)
    currency = Column(String, default="NGN", nullable=False)
    features = Column(JSON, nullable=False)  # Feature details and limits
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_recommended = Column(Boolean, default=False, nullable=False)  # Show as recommended
    sort_order = Column(Integer, default=0, nullable=False)  # Display order
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    created_by_admin_id = Column(Integer, nullable=True)  # Admin who created/updated

    users = relationship("User", back_populates="subscription_plan")

