from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from .user import UserProfile
from .job import JobInDB

class Applicant(BaseModel):
    id: int
    first_name: str
    last_name: str
    headline: Optional[str] = None
    avatar_url: Optional[str] = None
    rating: Optional[float] = None
    created_at: datetime
    cover_letter: Optional[str] = None
    proposal: Optional[str] = None

    class Config:
        from_attributes = True


class ApplicantProfile(BaseModel):
    application_id: int
    status: str
    applied_at: Optional[datetime] = None
    proposed_budget: float
    cover_letter: Optional[str] = None
    worker: UserProfile
    job: JobInDB

    class Config:
        from_attributes = True
