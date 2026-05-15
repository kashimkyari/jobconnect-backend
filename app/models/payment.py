from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, JSON, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.db.base_class import Base

class PaymentType(str, enum.Enum):
    SUBSCRIPTION = "subscription"      # Employer's monthly subscription
    WALLET_FUNDING = "wallet_funding"  # Worker funding their wallet
    APPLICATION_FEE = "application_fee"  # Fee for job application
    ESCROW_PAYMENT = "escrow_payment"    # Initial escrow funding
    ESCROW_RELEASE = "escrow_release"    # Release of escrow funds
    COMMISSION = "commission"            # Platform commission
    WITHDRAWAL = "withdrawal"          # User withdrawal

class PaymentStatus(str, enum.Enum):
    PENDING = "pending"        # Initial state
    PROCESSING = "processing"  # Payment being processed
    COMPLETED = "completed"    # Successfully completed
    FAILED = "failed"         # Payment failed
    REFUNDED = "refunded"     # Payment refunded
    HELD = "held"            # Held in escrow

class Payment(Base):
    """
    Tracks all financial transactions in the system including:
    - Subscription payments
    - Wallet funding
    - Application fees
    - Escrow transactions
    - Platform commissions
    """
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), index=True)
    withdrawal_request_id = Column(Integer, ForeignKey("withdrawal_requests.id"), index=True, nullable=True)
    
    # Payment details
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="NGN")
    payment_type = Column(Enum(PaymentType, native_enum=False), nullable=False)
    status = Column(Enum(PaymentStatus, native_enum=False), default=PaymentStatus.PENDING)
    channel = Column(String)
    ip_address = Column(String)
    
    # Payment processing
    paystack_reference = Column(String, unique=True)
    virtual_account_number = Column(String)
    commission_amount = Column(Numeric(10, 2))
    
    # Additional info
    description = Column(String)
    payment_metadata = Column(JSON)  # Flexible storage for additional payment data
    
    # Tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="payments")
    job = relationship("Job", back_populates="payments")
    
    @property
    def reference(self):
        return self.paystack_reference

    @property
    def transaction_type(self):
        return self.payment_type
    job_application = relationship("JobApplication", back_populates="payment", uselist=False)
    escrow_payments = relationship("EscrowTransaction", 
                                 foreign_keys="[EscrowTransaction.payment_id]",
                                 back_populates="payment")
    escrow_releases = relationship("EscrowTransaction", 
                                 foreign_keys="[EscrowTransaction.release_payment_id]",
                                 back_populates="release_payment")
