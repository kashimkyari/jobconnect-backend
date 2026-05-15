from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Enum, Float, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from ..models.payment import PaymentStatus

from app.db.base_class import Base

class ApplicationStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWING = "reviewing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    OFFER_ACCEPTED = "offer_accepted"
    OFFER_DECLINED = "offer_declined"

class ContractStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(Enum(ApplicationStatus), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    application_id = Column(Integer, ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False, index=True)

    application = relationship("JobApplication", back_populates="status_history")

class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True, index=True)
    cover_letter = Column(Text, nullable=True)
    video_introduction_url = Column(String, nullable=True)
    proposed_budget = Column(Float, nullable=True)  # Can be NULL; backend will auto-populate with job_price
    previous_job_ids = Column(JSONB, nullable=True)  # List of completed job IDs worker is referencing
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING, index=True)
    contract_status = Column(Enum(ContractStatus), default=ContractStatus.PENDING, index=True)
    boosted = Column(Boolean, default=False)
    
    # Payment tracking
    payment_required = Column(Boolean, default=False)
    payment_id = Column(Integer, ForeignKey("payments.id"), index=True)
    payment_status = Column(Enum(PaymentStatus), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Foreign Keys
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    worker_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Relationships
    job = relationship("Job", back_populates="applications")
    worker = relationship("User", back_populates="jobs_applied")
    payment = relationship("Payment", back_populates="job_application")
    status_history = relationship("ApplicationStatusHistory", back_populates="application", cascade="all, delete-orphan")
