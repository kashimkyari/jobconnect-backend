from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Numeric, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.db.base_class import Base
from app.models.enums import TaxPreference, WithdrawalRequestStatus


class WithdrawalRequest(Base):
    """
    Represents a user's withdrawal request that requires admin approval.
    Funds are held immediately upon request creation, and only released
    upon admin approval when the actual Paystack transfer is initiated.
    """
    __tablename__ = "withdrawal_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    
    # Withdrawal amounts
    amount = Column(Numeric(10, 2), nullable=False)  # Requested withdrawal amount
    tax_amount = Column(Numeric(10, 2), nullable=False, default=0.0)  # Calculated tax
    tax_preference = Column(Enum(TaxPreference, native_enum=False), nullable=False)  # BEFORE or AFTER
    total_amount = Column(Numeric(10, 2), nullable=False)  # amount + tax (if BEFORE) or final amount (if AFTER)
    
    # Status tracking
    status = Column(Enum(WithdrawalRequestStatus, native_enum=False), default=WithdrawalRequestStatus.PENDING, index=True)
    
    # Admin approval tracking
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Admin who approved/declined
    admin_notes = Column(Text)  # Notes from admin (e.g., reason for decline)
    
    # Payment reference after approval
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)  # Links to Payment record if approved
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    approved_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="withdrawal_requests")
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    bank_account = relationship("BankAccount", back_populates="withdrawal_requests")
    payment = relationship("Payment", foreign_keys=[payment_id], uselist=False)
    disputes = relationship("Dispute", foreign_keys="[Dispute.withdrawal_request_id]", back_populates="withdrawal_request", lazy="select")

    def __repr__(self):
        return f"<WithdrawalRequest(id={self.id}, user_id={self.user_id}, amount={self.amount}, status={self.status})>"
