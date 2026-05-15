from pydantic import BaseModel, EmailStr, Field, computed_field
from datetime import datetime, time
from typing import Optional
from app.models.enums import BookingStatus
from app.models.payment import PaymentStatus

class BookingCreate(BaseModel):
    """Schema for creating a new booking request"""
    service_id: int
    start_date: datetime
    start_time: Optional[time] = None
    duration_hours: int = Field(..., gt=0, le=168)  # Max 1 week booking
    hourly_rate: float = Field(..., gt=0)
    total_price: float = Field(..., gt=0)
    message: Optional[str] = Field(None, max_length=1000)
    address: Optional[str] = Field(None, max_length=255)
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "service_id": 1,
                "start_date": "2026-02-15T10:00:00",
                "start_time": "10:00:00",
                "duration_hours": 4,
                "hourly_rate": 50000.0,
                "total_price": 200000.0,
                "message": "Please bring your own tools",
                "address": "12 Adeola Odeku St, Victoria Island",
                "latitude": 6.4311,
                "longitude": 3.4510
            }
        }

class BookingUpdate(BaseModel):
    """Schema for updating booking status (worker response)"""
    status: BookingStatus
    worker_notes: Optional[str] = Field(None, max_length=500)

    class Config:
        json_schema_extra = {
            "example": {
                "status": "accepted",
                "worker_notes": "Looking forward to working with you!"
            }
        }

class BookingServiceInfo(BaseModel):
    """Service info included in booking response"""
    id: int
    name: str
    description: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None

    class Config:
        from_attributes = True

class BookingWorkerInfo(BaseModel):
    """Worker info included in booking response"""
    id: int
    first_name: str
    last_name: str
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    reputation_score: float = 0.0

    class Config:
        from_attributes = True
    
    @computed_field  # type: ignore[misc]
    @property
    def full_name(self) -> str:
        """Computed full name from first_name and last_name"""
        return f"{self.first_name} {self.last_name}".strip()

class BookingEmployerInfo(BaseModel):
    """Employer info included in booking response with comprehensive details"""
    id: int
    first_name: str
    last_name: str
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    reputation_score: float = 0.0
    is_verified: bool = False
    is_kyc_verified: bool = False

    class Config:
        from_attributes = True

class BookingResponse(BaseModel):
    """Full booking details response"""
    id: int
    service_id: int
    employer_id: int
    worker_id: int
    status: BookingStatus
    start_date: datetime
    start_time: Optional[time] = None
    duration_hours: int
    estimated_end_date: Optional[datetime] = None
    hourly_rate: float
    total_price: float
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    payment_status: Optional[PaymentStatus] = None
    message: Optional[str] = None
    worker_notes: Optional[str] = None
    employer_review: Optional[str] = None
    employer_rating: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    worker_completed: bool = False
    employer_completed: bool = False
    completion_state: str = "none"
    
    # Nested relationships
    service: Optional[BookingServiceInfo] = None
    employer: Optional[BookingEmployerInfo] = None
    worker: Optional[BookingWorkerInfo] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "service_id": 5,
                "employer_id": 10,
                "worker_id": 20,
                "status": "accepted",
                "start_date": "2026-02-15T10:00:00",
                "start_time": "10:00:00",
                "duration_hours": 4,
                "estimated_end_date": "2026-02-15T14:00:00",
                "hourly_rate": 50000.0,
                "total_price": 200000.0,
                "address": "12 Adeola Odeku St, Victoria Island",
                "latitude": 6.4311,
                "longitude": 3.4510,
                "payment_status": "completed",
                "message": "Please bring your own tools",
                "worker_notes": "Looking forward to working with you!",
                "employer_review": "Great job! Very professional.",
                "employer_rating": 4.5,
                "created_at": "2026-02-12T15:30:00",
                "updated_at": "2026-02-12T15:45:00",
                "accepted_at": "2026-02-12T15:45:00",
                "worker_completed": True,
                "employer_completed": False,
                "completion_state": "worker_marked_complete",
                "service": {
                    "id": 5,
                    "name": "House Cleaning",
                    "description": "Professional house cleaning",
                    "city": "Lagos",
                    "country": "Nigeria"
                },
                "employer": {
                    "id": 10,
                    "first_name": "John",
                    "last_name": "Doe",
                    "avatar_url": "https://example.com/avatar.jpg",
                    "phone": "08012345678",
                    "email": "john@example.com",
                    "reputation_score": 4.5,
                    "is_verified": True,
                    "is_kyc_verified": True
                },
                "worker": {
                    "id": 20,
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "avatar_url": "https://example.com/avatar2.jpg",
                    "phone": "08087654321",
                    "reputation_score": 4.8
                }
            }
        }

class BookingListResponse(BaseModel):
    """Paginated list of bookings"""
    total: int
    skip: int
    limit: int
    items: list[BookingResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "total": 10,
                "skip": 0,
                "limit": 20,
                "items": []
            }
        }
