from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base

class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

class TransactionType(str, enum.Enum):
    WALLET_FUNDING = "wallet_funding"
    WALLET_WITHDRAWAL = "wallet_withdrawal"
    ESCROW_PAYMENT = "escrow_payment"
    ESCROW_HOLD = "escrow_hold"
    ESCROW_RELEASE = "escrow_release"
    SUBSCRIPTION_PAYMENT = "subscription_payment"
    REFUND = "refund"
    BOOST = "boost"
    STREAK = "streak"

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    platform_fee = Column(Numeric(10, 2), nullable=False, default=0.0)
    commission = Column(Numeric(10, 2), nullable=False, default=0.0)
    status = Column(Enum(TransactionStatus, native_enum=False), default=TransactionStatus.PENDING)
    reference = Column(String, unique=True, index=True)
    description = Column(String)
    transaction_type = Column(Enum(TransactionType, native_enum=False), nullable=False)
    
    # Idempotency support - prevents duplicate transactions on retries
    idempotency_key = Column(String, nullable=True, index=True)  # Unique per request
    
    # Link related transactions (e.g., ESCROW_HOLD → ESCROW_RELEASE)
    related_transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="transactions")
    job = relationship("Job")
