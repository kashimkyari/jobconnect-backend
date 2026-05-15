from pydantic import BaseModel, Field, condecimal
from typing import Optional
from datetime import datetime
from enum import Enum

class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"

class PaymentType(str, Enum):
    JOB_PAYMENT = "job_payment"
    REFUND = "refund"
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"

# Base Schema
class PaymentBase(BaseModel):
    amount: condecimal(decimal_places=2, ge=0) = Field(...)
    payment_type: PaymentType
    description: Optional[str] = None
    reference_id: Optional[int] = None  # e.g., job_id for job payments

# Request Schemas
class PaymentCreate(PaymentBase):
    """Schema for creating a new payment. Inherits all fields from PaymentBase."""

class PaymentRefund(BaseModel):
    reason: str = Field(..., min_length=5)

class WithdrawalRequest(BaseModel):
    amount: condecimal(decimal_places=2, ge=0) = Field(...)
    bank_code: str
    account_number: str

class WithdrawalRequestSubmit(BaseModel):
    """Schema for submitting a new withdrawal request"""
    bank_account_id: int = Field(..., gt=0, description="ID of user's bank account")
    amount: condecimal(decimal_places=2, ge=0) = Field(..., description="Amount to withdraw (net amount)")

# Response Schemas
class PaymentInDB(PaymentBase):
    id: int
    payer_id: int
    payee_id: Optional[int]
    status: PaymentStatus
    transaction_reference: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

class PaymentResponse(BaseModel):
    payment_id: int
    authorization_url: Optional[str]
    reference: str
    status: PaymentStatus
    amount: condecimal(decimal_places=2, ge=0)
    fee: condecimal(decimal_places=2, ge=0)
    total_amount: condecimal(decimal_places=2, ge=0)

class VirtualAccountResponse(BaseModel):
    account_name: str
    account_number: str
    bank_name: str
    reference: str

class PaymentSummary(BaseModel):
    total_received: float
    total_paid: float
    pending_amount: float
    available_balance: float

class PaymentDetails(PaymentInDB):
    payer_name: str
    payee_name: Optional[str]
    job_title: Optional[str]  # For job payments
