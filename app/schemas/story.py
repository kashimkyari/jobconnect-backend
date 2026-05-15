from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from app.models.story import MediaType


# ========== Story Creation (Request) ==========

class StoryCreate(BaseModel):
    """Schema for creating a new story"""
    service_id: Optional[int] = Field(None, description="ID of the service being showcased")
    job_id: Optional[int] = Field(None, description="ID of the job being showcased")
    caption: Optional[str] = Field(None, max_length=500, description="Story caption/description")
    service_name: str = Field(..., min_length=1, max_length=100, description="Name of the service")
    service_desc: Optional[str] = Field(None, max_length=500, description="Service description")
    price: Optional[float] = Field(None, ge=0, description="Price (optional, can override service price)")
    duration: Optional[int] = Field(None, ge=1, description="Duration in days")
    media_type: MediaType = Field(MediaType.IMAGE, description="Type of media (image or video)")


# ========== Availability Schema ==========

class AvailabilitySlot(BaseModel):
    """A single availability slot"""
    day: str = Field(..., description="Day name (e.g., 'monday', 'tuesday')")
    slots: List[str] = Field(default_factory=list, description="List of time slots (e.g., ['9:00 AM', '2:00 PM'])")


# ========== Worker Summary (for Story Feed) ==========

class WorkerSummaryForStory(BaseModel):
    """Worker information to include in story feed"""
    id: int
    first_name: str
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    reputation_score: float = 0.0
    
    class Config:
        from_attributes = True


# ========== Story Response ==========

class StoryResponse(BaseModel):
    """Full story object for API responses"""
    id: int
    worker_id: int
    service_id: Optional[int] = None
    job_id: Optional[int] = None
    media_url: str
    media_type: MediaType
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None
    service_name: str
    service_desc: Optional[str] = None
    price: Optional[float] = None
    duration: Optional[int] = None
    worker_availability: Optional[List[AvailabilitySlot]] = None
    view_count: int
    is_active: bool
    expires_at: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True


# ========== Story Feed Response (enriched with worker data) ==========

class StoryFeedItem(BaseModel):
    """Story entry in feed with enriched worker information"""
    id: int
    worker_id: int
    creator_role: Optional[str] = Field(None, description="Role of story creator (worker or employer)")
    worker_name: str = Field(..., description="First and last name concatenated")
    worker_avatar: Optional[str] = None
    worker_rating: float = Field(default=0.0, description="From reputation_score")
    worker_review_count: int = Field(default=0, description="Number of reviews")
    worker_location: Optional[str] = Field(None, description="Worker's city or location")
    
    media_url: str
    media_type: MediaType
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None
    service_id: Optional[int] = None
    job_id: Optional[int] = None
    service_name: str
    service_desc: Optional[str] = None
    service_location: Optional[str] = Field(None, description="Service city/location")
    price: Optional[float] = None
    duration: Optional[int] = None
    
    availability: Optional[List[AvailabilitySlot]] = Field(
        default_factory=list, 
        description="Worker availability (from worker_availability)"
    )
    
    seen: bool = Field(default=False, description="Whether current user has viewed this story")
    view_count: int
    expires_at: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True


class StoryFeedResponse(BaseModel):
    """Response wrapper for story feed"""
    stories: List[StoryFeedItem]


# ========== Story View Response ==========

class StoryViewResponse(BaseModel):
    """Response after marking a story as viewed"""
    success: bool
    view_count: int
    message: str = "Story marked as viewed"


# ========== Worker Own Stories Response ==========

class ViewerSummary(BaseModel):
    """Summary of a viewer who viewed a story"""
    viewer_id: int
    viewer_name: str
    viewer_avatar: Optional[str] = None
    viewed_at: datetime


class StoryWithViewers(BaseModel):
    """Story with paginated list of viewers"""
    id: int
    media_url: str
    media_type: MediaType
    job_id: Optional[int] = None
    caption: Optional[str] = None
    service_name: str
    view_count: int
    viewers: List[ViewerSummary] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime
    is_active: bool
    
    class Config:
        from_attributes = True


class WorkerStoriesResponse(BaseModel):
    """Response for /api/stories/mine"""
    stories: List[StoryWithViewers]
    total_count: int


class StoryViewersResponse(BaseModel):
    """Paginated viewer list for a single story."""
    story_id: int
    view_count: int
    total_count: int
    viewers: List[ViewerSummary] = Field(default_factory=list)


# ========== Error Response ==========

class ErrorResponse(BaseModel):
    """Standard error response"""
    detail: str
    status_code: int
