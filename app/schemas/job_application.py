from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from .payment import PaymentStatus
from .user import WorkerInDB
from .enums import JobApplicationStatus, ContractStatus

class JobApplicationBase(BaseModel):
    cover_letter: str = Field(..., min_length=5)
    proposed_budget: Optional[float] = Field(None, gt=0, description="Worker's proposed budget. If not provided, defaults to job's price.")
    previous_job_ids: Optional[List[int]] = Field(default=None, description="IDs of completed jobs worker is referencing")

class JobApplicationCreate(JobApplicationBase):
    """Schema for creating a new job application."""
    payment_required: bool = False
    payment_id: Optional[int] = None

    @model_validator(mode='before')
    def validate_payment(cls, values):
        payment_required = values.get('payment_required')
        payment_id = values.get('payment_id')

        if payment_required and not payment_id:
            raise ValueError('payment_id is required when payment is required')
        
        return values

class JobApplicationUpdate(BaseModel):
    cover_letter: Optional[str] = Field(None, min_length=5)
    proposed_budget: Optional[float] = Field(None, gt=0)
    status: Optional[JobApplicationStatus] = None

class JobApplicationStatusUpdate(BaseModel):
    status: str  # 'accepted', 'rejected', 'withdrawn'
    notes: Optional[str] = None

class ApplicationStatusHistoryInDB(BaseModel):
    status: JobApplicationStatus
    created_at: datetime

    class Config:
        from_attributes = True

from app.schemas.job import JobInDB
from app.schemas.user import WorkerInDB

class ContractResponse(BaseModel):
    accept: bool

class HiringConfirmationRequest(BaseModel):
    """Request to confirm hiring with optional price negotiation"""
    negotiated_price: Optional[float] = Field(None, gt=0, description="New price if employer is counter-offering, or worker accepts with this price")
    contract_details: Optional[str] = Field(None, description="Additional contract details or notes")
    action: str = Field(..., description="'accept' to accept proposed price, 'negotiate' to counter-offer")

class HiringConfirmationResponse(BaseModel):
    """Response when employer confirms hiring"""
    application_id: int
    job_id: int
    worker_id: int
    original_price: float
    negotiated_price: Optional[float]
    status: str  # 'accepted' if worker agreed, 'pending_worker_response' if counter-offered
    contract_details: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class JobApplicationInDB(JobApplicationBase):
    id: int
    job_id: int
    worker_id: int
    status: JobApplicationStatus
    contract_status: ContractStatus
    boosted: bool = False
    payment_required: bool
    payment_id: Optional[int]
    payment_status: Optional[PaymentStatus]
    created_at: datetime
    updated_at: Optional[datetime] = None
    status_history: List[ApplicationStatusHistoryInDB] = []
    job: "JobInDB"
    worker: "WorkerInDB"
    has_reviewed: Optional[bool] = None

    class Config:
        from_attributes = True


class JobApplicationAdminInDB(JobApplicationInDB):
    status_history: List[ApplicationStatusHistoryInDB] = Field([], exclude=True)


JobApplicationInDB.model_rebuild()
JobApplicationAdminInDB.model_rebuild()
