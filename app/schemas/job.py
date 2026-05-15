from pydantic import BaseModel, Field, condecimal, model_validator, field_validator
from typing import Optional, List, TYPE_CHECKING, Union
from decimal import Decimal
from datetime import datetime
from enum import Enum

from .file import FileInDB
from .review import ReviewInDB, ReviewWithUserDetails, ReviewStats
from .user import UserInDB
from .enums import JobApplicationStatus, ContractStatus


class JobStatus(str, Enum):
    """Core job statuses - simplified from 7 to 4 core statuses"""
    DRAFT = "draft"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class CompletionStatus(str, Enum):
    WAITING_FOR_EMPLOYER = "waiting_for_employer"
    COMPLETED = "completed"


class JobLocationType(str, Enum):
    REMOTE = "remote"
    ONSITE = "onsite"
    HYBRID = "hybrid"

class JobType(str, Enum):
    ONE_TIME = "one_time"
    PART_TIME = "part_time"
    FULL_TIME = "full_time"

class ExperienceLevel(str, Enum):
    ENTRY = "entry"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"

class PaymentType(str, Enum):
    FIXED_PRICE = "fixed_price"
    HOURLY_RATE = "hourly_rate"


class JobBase(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=5)
    experience_level: Optional[ExperienceLevel] = None
    payment_type: Optional[PaymentType] = None
    hourly_rate: Optional[condecimal(decimal_places=2, ge=0)] = None
    estimated_hours: Optional[int] = Field(None, gt=0)
    country: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = Field(None, description="GPS latitude coordinate")
    longitude: Optional[float] = Field(None, description="GPS longitude coordinate")
    category_id: Union[str, int] = Field(..., description="The ID of the category this job belongs to (string e.g., 'healthcare', 'cleaning' or integer category ID)")
    job_price: Optional[condecimal(decimal_places=2, gt=0)] = Field(None, description="Fixed price for the job (required if payment_type is fixed_price, optional for hourly_rate)")
    location_type: JobLocationType
    job_type: Optional[JobType] = None
    tags: Optional[List[str]] = None
    is_high_value: bool = Field(default=False, description="Whether this job requires escrow payment")
    escrow_required: bool = Field(default=False, description="Whether escrow payment has been set up")
    commission_rate: float = Field(default=0.10, ge=0, le=1, description="Platform commission rate")
    contract_details: Optional[str] = Field(None, description="The contract for the job")
    is_archived: bool = Field(default=False, description="Whether job is archived")
    dispute_status: Optional[str] = Field(None, description="Dispute status if under dispute (DISPUTED, RESOLVED, CANCELLED, etc.)")

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda d: f"{d:.2f}"
        }

class JobCreate(JobBase):
    """Schema for creating a new job. Inherits all fields from JobBase."""
    attachment_ids: Optional[List[int]] = None
    repeated_from_job_id: Optional[int] = None

    @field_validator('category_id', mode='before')
    @classmethod
    def convert_category_id(cls, v):
        """Convert integer category_id to string for backward compatibility."""
        if isinstance(v, int):
            if v <= 0:
                raise ValueError('category_id must be a positive integer or non-empty string')
            return str(v)
        if isinstance(v, str):
            if not v or not v.strip():
                raise ValueError('category_id must be a non-empty string')
            return v.strip()
        raise ValueError('category_id must be a string or integer')

    @model_validator(mode='after')
    def validate_payment_configuration(self):
        """Validate that payment_type and payment amounts are properly configured."""
        payment_type = self.payment_type
        job_price = self.job_price
        hourly_rate = self.hourly_rate
        estimated_hours = self.estimated_hours

        # If payment_type is fixed_price, job_price is required
        if payment_type == PaymentType.FIXED_PRICE or payment_type == 'fixed_price':
            if job_price is None:
                raise ValueError('job_price is required when payment_type is fixed_price')
            if job_price <= 0:
                raise ValueError('job_price must be greater than 0')
        
        # If payment_type is hourly_rate, both hourly_rate and estimated_hours are required
        elif payment_type == PaymentType.HOURLY_RATE or payment_type == 'hourly_rate':
            if hourly_rate is None:
                raise ValueError('hourly_rate is required when payment_type is hourly_rate')
            if hourly_rate <= 0:
                raise ValueError('hourly_rate must be greater than 0')
            if estimated_hours is None:
                raise ValueError('estimated_hours is required when payment_type is hourly_rate')
            if estimated_hours <= 0:
                raise ValueError('estimated_hours must be greater than 0')
        
        return self

class JobUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=5, max_length=100)
    description: Optional[str] = Field(None, min_length=5)
    requirements: Optional[str] = None
    job_price: Optional[condecimal(decimal_places=2, gt=0)] = Field(None, description="Fixed price for the job")
    location: Optional[str] = None
    is_remote: Optional[bool] = None
    status: Optional[JobStatus] = None
    job_type: Optional[JobType] = None
    tags: Optional[List[str]] = None
    attachment_ids: Optional[List[int]] = None

from .user import UserInDB


class ActiveJob(JobBase):
    id: int
    employer_id: int
    worker_id: Optional[int] = None
    repeated_from_job_id: Optional[int] = None
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    worker: Optional[UserInDB] = None
    employer: Optional[UserInDB] = None

    class Config:
        from_attributes = True


class JobInDB(JobBase):
    id: int
    repeated_from_job_id: Optional[int] = None
    skills_required: Optional[List[str]] = None
    location: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_type: Optional[JobLocationType] = None
    category_name: Optional[str] = None
    confirmed_price: Optional[Decimal] = None  # Final negotiated price after hiring
    employer_id: int
    worker: Optional[UserInDB] = None
    employer_first_name: Optional[str] = None
    employer_last_name: Optional[str] = None
    employer_avatar_url: Optional[str] = None
    employer_phone: Optional[str] = None
    employer_email: Optional[str] = None
    employer: Optional[UserInDB] = None
    employer_review_stats: Optional[ReviewStats] = None
    status: JobStatus
    completion_status: Optional[CompletionStatus] = None
    created_at: datetime
    updated_at: datetime
    hired_at: Optional[datetime] = None
    completed_at: Optional[datetime]
    attachments: List[FileInDB] = []
    reviews: List[ReviewInDB] = []
    all_reviews: List[ReviewWithUserDetails] = []
    is_new: bool = False
    worker_completed: bool = False
    employer_completed: bool = False
    distance_km: Optional[float] = Field(None, description="Distance in kilometers from user's location")
    distance_display: Optional[str] = Field(None, description="Formatted distance string (e.g., '12 km away')")

    class Config:
        from_attributes = True


class EmployerJobDetail(JobInDB):
    is_active: bool
    applications_count: int
    budget_formatted: str
    skills_required: List[str]
    worker_completed: bool = False
    employer_completed: bool = False


class WorkerJobDetail(JobInDB):
    is_active: bool
    applications_count: int
    budget_formatted: str
    skills_required: List[str]
    application_status: Optional[JobApplicationStatus] = None
    contract_status: Optional[ContractStatus] = None
    boosted: bool = False
    worker_completed: bool = False
    employer_completed: bool = False
    is_hired_worker: bool = False
    distance_km: Optional[float] = Field(None, description="Distance in kilometers from worker's location")
    distance_display: Optional[str] = Field(None, description="Formatted distance string (e.g., '12 km away')")

from .job_with_applications import JobWithApplications
from .job_with_application_count import JobWithApplicationCount

JobInDB.model_rebuild()
EmployerJobDetail.model_rebuild()
WorkerJobDetail.model_rebuild()
