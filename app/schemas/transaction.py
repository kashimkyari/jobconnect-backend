from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class TransactionBase(BaseModel):
    amount: float
    platform_fee: Optional[float] = 0.0
    commission: Optional[float] = 0.0
    job_id: Optional[int] = None

class TransactionCreate(TransactionBase):
    status: Optional[str] = None
    reference: Optional[str] = None
    description: Optional[str] = None
    transaction_type: str
    idempotency_key: Optional[str] = None
    related_transaction_id: Optional[int] = None

class TransactionInDB(TransactionBase):
    id: int
    user_id: int
    status: str
    reference: Optional[str] = None
    description: Optional[str] = None
    transaction_type: str
    idempotency_key: Optional[str] = None
    related_transaction_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InitializePaymentResponse(BaseModel):
    """Response from Paystack when initializing a payment"""
    authorization_url: str
    access_code: str
    reference: str

    class Config:
        from_attributes = True


class WithdrawalRequest(BaseModel):
    amount: float
    bank_account_id: Optional[int] = None
    bank_code: Optional[str] = None
    account_number: Optional[str] = None
    bank_name: Optional[str] = None
