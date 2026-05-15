from pydantic import BaseModel, Field, condecimal, root_validator
from typing import Optional
from datetime import datetime

# Base Schema
class ReviewBase(BaseModel):
    rating: condecimal(ge=1, le=5, decimal_places=1) = Field(...)
    comment: Optional[str] = Field(None, min_length=1, max_length=500)
    job_id: Optional[int] = None
    service_id: Optional[int] = None

# Request Schemas
class ReviewCreate(ReviewBase):
    reviewee_id: int
    
    @root_validator(skip_on_failure=True)
    def validate_job_or_service(cls, values):
        """Ensure either job_id or service_id is provided, but not both."""
        job_id = values.get('job_id')
        service_id = values.get('service_id')
        
        if not job_id and not service_id:
            raise ValueError('Either job_id or service_id must be provided')
        if job_id and service_id:
            raise ValueError('Cannot provide both job_id and service_id')
        
        return values

class ReviewUpdate(BaseModel):
    comment: Optional[str] = Field(None, min_length=1)
    rating: Optional[condecimal(ge=1, le=5, decimal_places=1)] = None

# Response Schemas
class ReviewInDB(ReviewBase):
    id: int
    reviewer_id: int
    reviewee_id: int
    created_at: datetime
    updated_at: datetime

    # User details
    reviewee_firstname: Optional[str] = None
    reviewee_lastname: Optional[str] = None
    reviewee_avatar: Optional[str] = None
    reviewer_firstname: Optional[str] = None
    reviewer_lastname: Optional[str] = None
    reviewer_avatar: Optional[str] = None
    reviewer_name: Optional[str] = None
    job_title: Optional[str] = None
    time_ago: Optional[str] = None

    class Config:
        from_attributes = True

    @root_validator(pre=True)
    def load_user_details(cls, values):
        if isinstance(values, dict):
            if 'reviewee' in values and values['reviewee']:
                values['reviewee_firstname'] = values['reviewee'].first_name
                values['reviewee_lastname'] = values['reviewee'].last_name
                values['reviewee_avatar'] = values['reviewee'].avatar_url
            if 'reviewer' in values and values['reviewer']:
                values['reviewer_firstname'] = values['reviewer'].first_name
                values['reviewer_lastname'] = values['reviewer'].last_name
                values['reviewer_avatar'] = values['reviewer'].avatar_url
        return values

class ReviewWithUsers(ReviewInDB):
    reviewer_name: str
    reviewer_avatar: Optional[str]
    reviewee_name: str
    reviewee_avatar: Optional[str]
    job_title: str

class ReviewWithUserDetails(BaseModel):
    """Review with full user details and role indicators for job context."""
    id: int
    rating: condecimal(ge=1, le=5, decimal_places=1)
    comment: str
    job_id: int
    reviewer_id: int
    reviewer_name: str
    reviewer_avatar: Optional[str]
    reviewer_role: str  # "employer" or "worker" in the context of this job
    reviewee_id: int
    reviewee_name: str
    reviewee_avatar: Optional[str]
    reviewee_role: str  # "employer" or "worker" in the context of this job
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ReviewStats(BaseModel):
    average_rating: float
    total_reviews: int
    rating_distribution: dict[int, int]  # e.g., {5: 10, 4: 5, 3: 3, 2: 1, 1: 0}

class ReviewCreateResponse(BaseModel):
    """Response after successfully creating a review with full context."""
    id: int
    rating: condecimal(ge=1, le=5, decimal_places=1)
    comment: str
    job_id: Optional[int] = None
    service_id: Optional[int] = None
    reviewer_id: int
    reviewee_id: int
    created_at: datetime
    updated_at: datetime
    
    # Reviewer details
    reviewer_name: str
    reviewer_avatar: Optional[str]
    
    # Reviewee details
    reviewee_name: str
    reviewee_avatar: Optional[str]
    reviewee_email: Optional[str]
    
    # Context
    job_title: Optional[str] = None
    service_name: Optional[str] = None
    job_description: Optional[str] = None
    
    # Success message
    success: bool = True
    message: str = "Review submitted successfully"

    class Config:
        from_attributes = True
