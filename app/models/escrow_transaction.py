from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.db.base_class import Base

class EscrowStatus(str, enum.Enum):
    FUNDED = "funded"      # Initial state when escrow is created
    PENDING = "pending"    # Awaiting confirmation or review
    RELEASED = "released"  # Funds released to worker
    WITHHELD = "withheld"  # Funds held due to dispute
    REFUNDED = "refunded"  # Funds returned to employer
    DISPUTED = "disputed"  # Under dispute resolution

class EscrowTransaction(Base):
    """
    Tracks escrow transactions between employers and workers.
    Handles the 10% commission on high-value jobs.
    """
    __tablename__ = "escrow_transactions"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    worker_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Payment details
    amount = Column(Float, nullable=False)
    commission_rate = Column(Float, default=0.10)  # 10% default
    commission_amount = Column(Float, nullable=False)
    net_amount = Column(Float, nullable=False)  # Amount after commission
    
    # Status and tracking
    status = Column(Enum(EscrowStatus), default=EscrowStatus.FUNDED)
    payment_id = Column(Integer, ForeignKey("payments.id"), index=True)
    release_payment_id = Column(Integer, ForeignKey("payments.id"), index=True)
    
    # Audit trail
    admin_notes = Column(String)
    dispute_reason = Column(String)
    resolution_notes = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    released_at = Column(DateTime)
    
    # Relationships
    job = relationship("Job", back_populates="escrow_transactions")
    employer = relationship("User", foreign_keys=[employer_id], back_populates="employer_escrows")
    worker = relationship("User", foreign_keys=[worker_id], back_populates="worker_escrows")
    payment = relationship("Payment", foreign_keys=[payment_id], back_populates="escrow_payments")
    release_payment = relationship("Payment", foreign_keys=[release_payment_id], back_populates="escrow_releases")
