from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import date, datetime
from enum import Enum
from app.schemas.worker_profile import RecentWorkInDB, UserServiceInDB, RecentWorkCreate, UserServiceCreate
from app.schemas.subscription import SubscriptionInDB
from app.schemas.transaction import TransactionInDB
from .review import ReviewInDB

class UserRole(str, Enum):
    ADMIN = "admin"
    EMPLOYER = "employer"
    WORKER = "worker"

class UserBase(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[UserRole] = None  # None for users before role selection

class UserCreate(UserBase):
    password: str
    referral_code: Optional[str] = None

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    paystack_customer_code: Optional[str] = None
    is_onboarding_complete: Optional[bool] = None
    onboarding_step: Optional[int] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    about_me: Optional[str] = None
    service_category: Optional[str] = None
    experience_level: Optional[str] = None
    skills: Optional[List[str]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    search_radius_km: Optional[int] = None

class UserInDB(UserBase):
    id: int
    is_active: bool
    is_verified: bool
    is_kyc_verified: bool
    kyc_status: Optional[str] = None
    is_onboarding_complete: bool
    avatar_url: Optional[str] = None
    headline: Optional[str] = None
    reputation_score: float = 0.0
    wallet_balance: Optional[float] = 0.0
    streak_count: int = 0
    last_streak_claim_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    distance_km: Optional[float] = None  # Distance in km from requester's location
    distance_display: Optional[str] = None  # Formatted distance string

    class Config:
        from_attributes = True

class UserOut(UserInDB):
    is_subscribed: bool = False

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int

class TokenData(BaseModel):
    user_id: Optional[int] = None
    role: Optional[str] = None

class WorkerInDB(UserInDB):
    pass

class EmployerInDB(UserInDB):
    pass

class UserRoleSwitch(BaseModel):
    role: UserRole

class UserProfile(UserOut):
    avg_rating: float = 0.0
    average_rating: float = 0.0
    reputation_score: float = 0.0
    total_reviews: int = 0
    average_service_price: Optional[float] = None
    is_onboarding_complete: bool
    total_jobs_posted: int = 0
    total_jobs_completed: int = 0
    profile_completion_percentage: int = 0
    subscription: Optional[SubscriptionInDB] = None
    recent_transactions: List[TransactionInDB] = []
    headline: Optional[str] = None
    location: Optional[str] = None
    about_me: Optional[str] = None
    service_category: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_level: Optional[str] = None
    recent_works: List[RecentWorkInDB] = []
    services_offered: List[UserServiceInDB] = []

class JobPosterProfile(UserOut):
    total_jobs_posted: int = 0
    total_jobs_completed: int = 0
    avg_rating: float = 0.0
    reviews: List[ReviewInDB] = []

class WorkerProfileUpdate(BaseModel):
    headline: Optional[str] = None
    location: Optional[str] = None
    about_me: Optional[str] = None
    service_category: Optional[str] = None
    avatar_url: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_level: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    recent_works: Optional[List[RecentWorkCreate]] = None
    services_offered: Optional[List[UserServiceCreate]] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    id_image_url: Optional[str] = None
    selfie_image_url: Optional[str] = None
    onboarding_step: Optional[int] = None
class LocationUpdate(BaseModel):
    """Schema for updating user location"""
    latitude: float
    longitude: float
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    search_radius_km: Optional[int] = Field(default=50, ge=1, le=500)

class LocationResponse(BaseModel):
    """Schema for location response"""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    search_radius_km: int = 50

    class Config:
        from_attributes = True

class UserProfileWithLocation(UserProfile):
    """User profile with location information"""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    search_radius_km: int = 50


class DailyClaimRequest(BaseModel):
    """Request schema for daily streak claim"""
    client_timezone: str = Field(default="UTC", description="User's timezone (e.g., 'Africa/Lagos', 'UTC')")


class DailyClaimResponse(BaseModel):
    """Response schema for successful daily streak claim"""
    streak_count: int = Field(description="Current streak day count")
    credits_awarded: float = Field(description="Credits awarded for this claim (in Naira)")
    total_credits: float = Field(description="Total wallet balance after claim (in Naira)")
    is_milestone: bool = Field(description="Whether this is a milestone day (3, 7, 14, 30, etc.)")
    next_milestone_day: Optional[int] = Field(description="Next milestone day after current")


class StreakHistoryDay(BaseModel):
    """Daily streak history item for a calendar date."""
    date: date
    claimed: bool


class StreakHistoryResponse(BaseModel):
    """Response schema for streak history screen."""
    streak_count: int
    last_streak_claim_at: Optional[datetime] = None
    first_streak_claim_at: Optional[datetime] = None
    total_claimed_days: int
    best_streak: int
    days_back: int
    calendar_start_date: date
    calendar_end_date: date
    has_history: bool
    days: List[StreakHistoryDay] = []
