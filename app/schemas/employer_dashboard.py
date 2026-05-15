from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from app.models.user import User


class ActivityType(str, Enum):
    JOB_APPLICATION = "job_application"
    JOB_COMPLETION = "job_completion"
    NEW_MESSAGE = "new_message"
    PROFILE_VIEW = "profile_view"
    JOB_POSTED = "job_posted"
    WORKER_HIRED = "worker_hired"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_SENT = "payment_sent"
    REVIEW_RECEIVED = "review_received"
    JOB_CANCELLED = "job_cancelled"
    DISPUTE_RAISED = "dispute_raised"
    PROFILE_UPDATE = "profile_update"
    WALLET_FUNDED = "wallet_funded"
    WITHDRAWAL_REQUEST = "withdrawal_request"
    WITHDRAWAL_COMPLETED = "withdrawal_completed"
    WITHDRAWAL_FAILED = "withdrawal_failed"


class EnrichedRecentActivitySchema(BaseModel):
    id: int
    user_id: int
    activity_type: ActivityType
    title: str
    subtitle: str
    description: str
    action_label: str  # e.g., "View Job", "Contact Worker", "Pay Invoice"
    target_id: Optional[int] = None  # Job ID, Worker ID, etc.
    target_name: Optional[str] = None  # Job title, Worker name, etc.
    target_image_url: Optional[str] = None  # Worker avatar, etc.
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime
    time_ago: str  # e.g., "2 hours ago"

    class Config:
        from_attributes = True


class DashboardMetricsSchema(BaseModel):
    active_jobs: int
    total_jobs: int
    new_applications: int
    total_applications: int
    pending_payments: float
    total_earnings: float
    wallet_balance: float
    profile_views_this_month: int
    profile_views_total: int
    average_rating: float
    total_reviews: int
    response_rate: float
    completion_rate: float
    completed_jobs: int
    active_jobs_trend: Optional[Dict[str, Any]] = None
    new_applications_trend: Optional[Dict[str, Any]] = None
    profile_views_trend: Optional[Dict[str, Any]] = None
    wallet_balance_trend: Optional[Dict[str, Any]] = None
    job_views_trend: Optional[Dict[str, Any]] = None
    completed_jobs_trend: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class JobAnalyticsDataSchema(BaseModel):
    total_applicants: int
    total_views: int
    posted_at: datetime

    class Config:
        from_attributes = True


class ActiveJobSchema(BaseModel):
    job_id: int
    title: str
    status: str
    created_at: datetime
    location: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    location_type: Optional[str] = None
    job_price: Optional[float] = None
    hourly_rate: Optional[float] = None
    estimated_hours: Optional[int] = None
    analytics: JobAnalyticsDataSchema

    class Config:
        from_attributes = True


class PaymentSummarySchema(BaseModel):
    total_earnings: float
    pending_payments: float
    released_payments: float
    wallet_balance: float
    total_transactions: int
    this_month_earnings: float
    last_transaction_date: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaymentHistorySchema(BaseModel):
    id: int
    job_id: Optional[int] = None
    job_title: Optional[str] = None
    worker_id: Optional[int] = None
    worker_name: Optional[str] = None
    amount: float
    status: str
    transaction_type: str  # "payment", "refund", "bonus", etc.
    created_at: datetime
    description: Optional[str] = None

    class Config:
        from_attributes = True


class JobApplicationDetailSchema(BaseModel):
    id: int
    job_id: int
    worker_id: int
    worker_name: str
    worker_avatar: Optional[str] = None
    worker_rating: float
    worker_completed_jobs: int
    proposal: Optional[str] = None
    status: str  # "pending", "accepted", "rejected", "withdrawn"
    applied_at: datetime
    response_time_hours: Optional[int] = None

    class Config:
        from_attributes = True


class WorkerListItemSchema(BaseModel):
    """Simplified worker schema for nearby/top workers display"""
    id: int
    first_name: str
    last_name: Optional[str] = None
    headline: Optional[str] = None
    avatar_url: Optional[str] = None
    reputation_score: float = 0.0
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None  # Distance in km from employer's location
    distance_display: Optional[str] = None  # Formatted distance string

    class Config:
        from_attributes = True


class ServiceListItemSchema(BaseModel):
    """Simplified service schema for nearby services display"""
    id: int
    name: str
    description: Optional[str] = None
    price: float
    image_url: Optional[str] = None
    category_name: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    worker: Optional[WorkerListItemSchema] = None
    distance_km: Optional[float] = None  # Distance in km from employer's location
    distance_display: Optional[str] = None  # Formatted distance string

    class Config:
        from_attributes = True


class EmployerDashboardSchema(BaseModel):
    stats: DashboardMetricsSchema
    recent_activity: List[EnrichedRecentActivitySchema]
    active_jobs: List[ActiveJobSchema]
    unread_notifications: int
    nearby_workers: List[WorkerListItemSchema] = []
    top_workers: List[WorkerListItemSchema] = []
    nearby_services: List[ServiceListItemSchema] = []

    class Config:
        from_attributes = True


class UnreadNotificationCountSchema(BaseModel):
    unread_count: int
    total_notifications: int

    class Config:
        from_attributes = True


class EmployerWalletSchema(BaseModel):
    balance: float
    total_in: float
    total_out: float
    recent_transactions: List[PaymentHistorySchema]

    class Config:
        from_attributes = True
