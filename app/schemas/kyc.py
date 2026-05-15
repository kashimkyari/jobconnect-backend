from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from .user import UserInDB

class DocumentType(str, Enum):
    PASSPORT = "passport"
    NATIONAL_ID = "national_id"
    DRIVERS_LICENSE = "drivers_license"
    DRIVER_LICENSE = "driver_license"

class VerificationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

# Liveness data schema
class LivenessCheckResult(BaseModel):
    blink: bool = False
    turn_left: bool = False
    turn_right: bool = False
    smile: bool = False
    anti_spoofing: bool = False
    overall_confidence: float = Field(..., ge=0, le=100)
    duration_ms: int = 0
    timestamp: str

class LivenessData(BaseModel):
    blink: bool = False
    turn_left: bool = False
    turn_right: bool = False
    smile: bool = False
    anti_spoofing: bool = False
    overall_confidence: float = Field(..., ge=0, le=100)
    duration_ms: int = 0
    timestamp: str

# Base Schema
class KYCSubmissionBase(BaseModel):
    document_type: DocumentType
    document_path: str
    selfie_path: Optional[str] = None
    selfie_paths: Optional[List[str]] = None
    liveness_data: Optional[LivenessData] = None

# Request Schemas
class KYCSubmissionCreate(BaseModel):
    document_type: DocumentType
    document_path: str
    selfie_path: Optional[str] = None
    selfie_paths: Optional[List[str]] = None
    liveness_data: Optional[LivenessData] = None
    liveness_token: Optional[str] = None  # JWT token from /verify/liveness endpoint

class KYCVerification(BaseModel):
    is_approved: bool
    notes: Optional[str] = None

# Response Schemas
class KYCSubmission(KYCSubmissionBase):
    id: int
    user_id: int
    status: VerificationStatus
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    verified_at: Optional[datetime]
    user: UserInDB

    class Config:
        from_attributes = True

class KYCStatus(BaseModel):
    is_verified: bool
    kyc_status: str
    latest_submission: Optional[KYCSubmission]
    total_attempts: int
    last_verification_date: Optional[datetime]

class KYCWithUser(KYCSubmission):
    user_name: str
    user_email: str
    user_phone: str
