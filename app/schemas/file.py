from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional, List
from enum import Enum

class FileCategory(str, Enum):
    AVATAR = "avatar"
    SERVICE_IMAGE = "service_image"
    JOB_ATTACHMENT = "job_attachment"
    KYC_DOCUMENT = "kyc_document"
    MESSAGE_ATTACHMENT = "message_attachment"
    PROFILE_DOCUMENT = "profile_document"
    STORY_MEDIA = "story_media"
    DISPUTE_EVIDENCE = "dispute_evidence"

# Base Schema
class FileBase(BaseModel):
    filename: str = Field(..., description="UUID-based filename")
    original_filename: str = Field(..., description="Original user filename")
    file_path: str = Field(..., description="Path relative to UPLOAD_DIR")
    file_type: str = Field(..., description="MIME type")
    file_size: int = Field(..., gt=0, description="Size in bytes")
    category: FileCategory
    reference_id: Optional[int] = Field(None, description="ID of related entity")
    reference_type: Optional[str] = Field(None, description="Type of related entity")

# Request Schemas
class FileCreate(BaseModel):
    category: FileCategory
    reference_id: Optional[int] = None
    reference_type: Optional[str] = None

class FileUpdate(BaseModel):
    original_filename: Optional[str] = None
    category: Optional[FileCategory] = None
    reference_id: Optional[int] = None
    reference_type: Optional[str] = None

# Response Schemas
class FileInDB(FileBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @validator("category", pre=True)
    def validate_category(cls, v):
        if isinstance(v, str):
            return FileCategory(v)
        return v

class FileWithReference(FileInDB):
    reference_title: Optional[str] = None  # Title/name of referenced entity
    reference_url: Optional[str] = None    # URL to referenced entity

class FileGroup(BaseModel):
    category: FileCategory
    files: List[FileInDB]
    total_size: int
    count: int
