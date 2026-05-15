from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base


class BoostType(str, enum.Enum):
    """Type of entity being boosted"""
    JOB = "job"
    SERVICE = "service"


class BoostTransaction(Base):
    """
    Tracks boost purchases for jobs and services.
    
    When a user purchases a boost:
    - Boost cost is deducted from their wallet
    - Boost is activated on the job/service
    - Boost expiry is set
    - Transaction is logged here for audit trail
    """
    __tablename__ = "boost_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    boost_type = Column(Enum(BoostType), nullable=False, index=True)  # "job" or "service"
    reference_id = Column(Integer, nullable=False, index=True)  # job_id or service_id
    cost = Column(Float, nullable=False)  # Cost of the boost (NGN)
    duration_days = Column(Integer, nullable=False)  # How many days the boost lasts (e.g., 7)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)  # When boost expires

    def __repr__(self):
        return f"<BoostTransaction(id={self.id}, user_id={self.user_id}, type={self.boost_type}, ref={self.reference_id})>"
