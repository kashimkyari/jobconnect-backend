from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base

class DisputeStatus(str, enum.Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    REJECTED = "rejected"

class DisputeType(str, enum.Enum):
    """Type of dispute"""
    JOB = "job"  # Job-related dispute
    WITHDRAWAL = "withdrawal"  # Withdrawal transfer failure

class Dispute(Base):
    __tablename__ = "disputes"

    id = Column(Integer, primary_key=True, index=True)
    
    # Dispute type determines which fields are used
    dispute_type = Column(Enum(DisputeType), default=DisputeType.JOB, index=True)
    
    # Job-based disputes
    job_id = Column(Integer, ForeignKey("jobs.id"), index=True, nullable=True)
    claimant_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    defendant_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    
    # Withdrawal-based disputes
    withdrawal_request_id = Column(Integer, ForeignKey("withdrawal_requests.id"), index=True, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)  # User affected by failed withdrawal
    
    reason = Column(Text, nullable=False)
    evidence_url = Column(Text, nullable=True)
    status = Column(Enum(DisputeStatus), default=DisputeStatus.OPEN)
    
    resolution = Column(Text)
    resolved_by_admin_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # For withdrawal disputes: action taken
    resolution_action = Column(String)  # "retry" or "refund"
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    resolved_at = Column(DateTime(timezone=True))

    # Relationships
    job = relationship("Job", back_populates="disputes", foreign_keys=[job_id], lazy='select')
    claimant = relationship("User", foreign_keys=[claimant_id], back_populates="disputes_claimed", lazy='select')
    defendant = relationship("User", foreign_keys=[defendant_id], back_populates="disputes_defended", lazy='select')
    resolved_by_admin = relationship("User", foreign_keys=[resolved_by_admin_id], back_populates="disputes_resolved", lazy='select')
    affected_user = relationship("User", foreign_keys=[user_id], back_populates="withdrawal_disputes", lazy='select')
    withdrawal_request = relationship("WithdrawalRequest", back_populates="disputes", foreign_keys=[withdrawal_request_id], lazy='select')
    messages = relationship("DisputeMessage", back_populates="dispute", cascade="all, delete-orphan", lazy="selectin")
    attachments = relationship("DisputeAttachment", back_populates="dispute", cascade="all, delete-orphan", lazy="selectin")

    # Alias claimant and defendant to employer and worker for easier access (job disputes only)
    employer = relationship(
        "User",
        secondary="jobs",
        primaryjoin="Dispute.job_id == Job.id",
        secondaryjoin="Job.employer_id == User.id",
        viewonly=True,
        uselist=False,
    )
    worker = relationship(
        "User",
        secondary="jobs",
        primaryjoin="Dispute.job_id == Job.id",
        secondaryjoin="Job.worker_id == User.id",
        viewonly=True,
        uselist=False,
    )
