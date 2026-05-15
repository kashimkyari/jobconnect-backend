from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from .user import UserOut
from .job import JobInDB

from ..models.dispute import DisputeStatus

class DisputeAttachmentBase(BaseModel):
    file_url: str
    file_type: str

class DisputeAttachmentCreate(DisputeAttachmentBase):
    pass

class DisputeAttachmentOut(DisputeAttachmentBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class DisputeMessageBase(BaseModel):
    message: str = Field(..., min_length=1)
    evidence_url: Optional[str] = None # Keeping for backward compat
    attachment_urls: Optional[List[str]] = None

class DisputeMessageCreate(DisputeMessageBase):
    pass

class DisputeMessageOut(DisputeMessageBase):
    id: int
    dispute_id: int
    sender_id: Optional[int] = None
    is_admin_reply: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    sender: Optional[UserOut] = None
    attachments: List[DisputeAttachmentOut] = []

    class Config:
        from_attributes = True

class DisputeBase(BaseModel):
    reason: str = Field(..., min_length=5)
    evidence_url: Optional[str] = None
    attachment_urls: Optional[List[str]] = None

class DisputeCreate(DisputeBase):
    job_id: int
    defendant_id: Optional[int] = None

class DisputeUpdate(BaseModel):
    status: Optional[DisputeStatus] = None
    resolution: Optional[str] = Field(None, min_length=5)
    resolution_action: Optional[str] = None  # e.g., 'refund', 'release', 'split'

class DisputeInDB(DisputeBase):
    id: int
    job_id: Optional[int] = None
    claimant_id: Optional[int] = None
    defendant_id: Optional[int] = None
    withdrawal_request_id: Optional[int] = None
    user_id: Optional[int] = None
    status: DisputeStatus
    dispute_type: str = "job"
    resolution: Optional[str] = None
    resolved_by_admin_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    job: Optional[JobInDB] = None

    class Config:
        from_attributes = True

class DisputeDetails(DisputeInDB):
    job: JobInDB
    claimant: UserOut
    defendant: UserOut
    resolved_by_admin: Optional[UserOut] = None
    messages: List[DisputeMessageOut] = []
    attachments: List[DisputeAttachmentOut] = []
