from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

from ..models.escrow_transaction import EscrowStatus

class EscrowTransactionBase(BaseModel):
    """Base Escrow Transaction Schema"""
    job_id: int = Field(..., description="ID of the job this escrow is for")
    amount: float = Field(..., gt=0, description="Total amount to be held in escrow")

class EscrowTransactionCreate(EscrowTransactionBase):
    """Schema for creating a new escrow transaction"""
    employer_id: int
    worker_id: int
    commission_rate: float = Field(default=0.10, ge=0, le=1)
    
    @validator('commission_rate')
    def validate_commission_rate(cls, v):
        if not 0 <= v <= 1:
            raise ValueError('Commission rate must be between 0 and 1')
        return v

class EscrowTransactionUpdate(BaseModel):
    """Schema for updating an escrow transaction"""
    status: Optional[EscrowStatus]
    admin_notes: Optional[str]
    dispute_reason: Optional[str]
    resolution_notes: Optional[str]

class EscrowTransactionInDB(EscrowTransactionBase):
    """Schema for escrow transaction in database"""
    id: int
    employer_id: int
    worker_id: int
    commission_rate: float
    commission_amount: float
    net_amount: float
    status: EscrowStatus
    payment_id: Optional[int]
    release_payment_id: Optional[int]
    admin_notes: Optional[str]
    dispute_reason: Optional[str]
    resolution_notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    released_at: Optional[datetime]

    class Config:
        from_attributes = True

class EscrowTransactionDetail(EscrowTransactionInDB):
    """Schema for detailed escrow transaction view"""
    employer_name: str
    worker_name: str
    job_title: str
    payment_reference: Optional[str]
    release_reference: Optional[str]

class EscrowDisputeCreate(BaseModel):
    """Schema for creating an escrow dispute"""
    reason: str = Field(..., min_length=5)
    evidence: Optional[str]

class EscrowResolutionCreate(BaseModel):
    """Schema for resolving an escrow dispute"""
    resolution: str = Field(..., min_length=5)
    action: str = Field(..., regex='^(release|refund|split)$')
    split_ratio: Optional[float] = Field(None, ge=0, le=1)
