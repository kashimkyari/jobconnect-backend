from pydantic import BaseModel, Field, conint
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from .payment import PaymentType, PaymentStatus, PaymentInDB
from ..models.escrow_transaction import EscrowStatus
from .user import UserInDB
from .dispute import DisputeInDB
from .recent_activity import RecentActivityOut
from .job import JobStatus, JobLocationType as LocationType, JobType
from .job_application import JobApplicationInDB
from .review import ReviewInDB, ReviewWithUserDetails
from .file import FileInDB

class AdminActionType(str, Enum):
    SUSPEND_USER = "suspend_user"
    VERIFY_USER = "verify_user"
    RESOLVE_DISPUTE = "resolve_dispute"
    MODERATE_CONTENT = "moderate_content"
    REFUND_PAYMENT = "refund_payment"

class ContentType(str, Enum):
    MESSAGE = "message"
    JOB = "job"
    REVIEW = "review"
    PROFILE = "profile"

# List Response Schemas
class PaginatedResponse(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool

class UserList(PaginatedResponse):
    users: List[Dict[str, Any]]

class JobInDB(BaseModel):
    id: int
    title: str
    description: str
    requirements: Optional[str]
    job_price: Optional[float] = None
    budget: Optional[float] = None  # legacy alias
    location: Optional[str]
    location_type: LocationType
    status: JobStatus
    employer: Optional[UserInDB]
    worker: Optional[UserInDB]
    applicant_count: int
    dispute_status: str
    payment_status: str
    created_at: datetime
    updated_at: datetime
    is_high_value: bool
    escrow_required: bool
    commission_rate: Optional[float]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

class AdminJobInDB(BaseModel):
    id: int
    title: str
    description: str
    requirements: Optional[str]
    job_price: Optional[float] = None
    budget: Optional[float] = None  # legacy alias
    location: Optional[str]
    location_type: LocationType
    status: JobStatus
    employer_id: int
    employer_first_name: str
    employer_last_name: str
    employer_avatar_url: Optional[str]
    employer_phone: str
    employer_email: str
    worker: Optional[UserInDB]
    applicant_count: int
    dispute_status: str
    payment_status: str
    created_at: datetime
    updated_at: datetime
    is_high_value: bool
    escrow_required: bool
    commission_rate: Optional[float]
    completed_at: Optional[datetime]
    category_name: Optional[str]
    completion_status: Optional[str]
    applications: List[JobApplicationInDB] = []
    all_reviews: List[ReviewWithUserDetails] = []
    category_id: Optional[str]
    job_type: Optional[JobType] = None
    tags: Optional[List[str]] = None
    attachments: List[FileInDB] = []
    payments: List[PaymentInDB] = []
    disputes: List[DisputeInDB] = []

    class Config:
        from_attributes = True

class JobList(PaginatedResponse):
    jobs: List[JobInDB]

class AdminJobMinimal(BaseModel):
    id: int
    title: str
    description: str
    status: JobStatus
    employer_name: str
    job_price: Optional[float] = None
    budget: Optional[float] = None  # legacy alias
    has_dispute: bool

    class Config:
        from_attributes = True

class AdminJobList(PaginatedResponse):
    jobs: List[AdminJobMinimal]


class JobApplicant(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    avatar_url: Optional[str]
    application_status: str
    application_date: datetime

    class Config:
        from_attributes = True


class JobApplicantList(PaginatedResponse):
    applicants: List[JobApplicant]

class UserSimple(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str

class DisputeAdminView(BaseModel):
    id: int
    job_id: int
    job_title: str
    employer: Optional[UserSimple]
    worker: Optional[UserSimple]
    status: str
    reason: str
    evidence_url: Optional[str] = None
    resolution: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]
    messages: List[DisputeInDB] = []

    class Config:
        from_attributes = True

class DisputeList(PaginatedResponse):
    disputes: List[DisputeAdminView]

class ContentModerationList(PaginatedResponse):
    content: List["ModeratedContent"]

class ReviewList(PaginatedResponse):
    reviews: List[Dict[str, Any]]

class BadgeList(PaginatedResponse):
    badges: List[Dict[str, Any]]

class RecentActivityList(PaginatedResponse):
    activities: List[RecentActivityOut]

# Query Parameter Schemas
class PaginationParams(BaseModel):
    page: Optional[int] = Field(1, ge=1, description="Page number")
    per_page: Optional[int] = Field(10, ge=1, le=100, description="Items per page")

class UserListParams(PaginationParams):
    role: Optional[str] = Field(None, pattern='^(worker|employer|admin)$')
    is_verified: Optional[bool] = None
    is_active: Optional[bool] = None
    search: Optional[str] = None

class JobListParams(PaginationParams):
    status: Optional[str] = None
    has_dispute: Optional[bool] = None
    employer_id: Optional[int] = None
    worker_id: Optional[int] = None
    search: Optional[str] = None

class DisputeListParams(PaginationParams):
    status: Optional[str] = Field(None, pattern='^(open|resolved|escalated)$')
    job_id: Optional[int] = None
    user_id: Optional[int] = None

class ContentModerationParams(PaginationParams):
    content_type: Optional[ContentType] = None
    status: Optional[str] = Field(None, pattern='^(pending|approved|removed)$')
    reporter_id: Optional[int] = None

# Request Schemas
class UserAction(BaseModel):
    action: Optional[str] = Field(None, pattern='^(suspend|activate|verify)$')
    reason: Optional[str] = Field(None, min_length=5)
    duration_days: Optional[int] = Field(None, ge=1, le=365)

class AdminDisputeResolution(BaseModel):
    resolution: str

class DisputeResolution(BaseModel):
    resolution: str = Field(..., pattern='^(refund|complete|cancel)$')
    notes: str = Field(..., min_length=5)
    winner_id: Optional[int] = None
    refund_amount: Optional[float] = Field(None, gt=0)

class ContentModeration(BaseModel):
    action: str = Field(..., pattern='^(remove|approve|flag)$')
    reason: str = Field(..., min_length=5)
    notify_user: bool = Field(default=True)

# Response Schemas
class AdminAction(BaseModel):
    id: int
    admin_id: int
    admin_name: str
    action_type: AdminActionType
    target_id: int
    target_type: str
    details: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True

class DashboardStats(BaseModel):
    total_users: int
    new_users_today: int
    active_users_last_7_days: int
    active_jobs: int
    completed_jobs: int
    total_disputes: int
    open_disputes: int
    pending_verifications: int
    platform_earnings: float
    platform_earnings_last_7_days: float
    user_growth_rate: float
    job_completion_rate: float

class TimeSeriesMetric(BaseModel):
    timestamp: datetime
    value: float

class PlatformMetrics(BaseModel):
    user_growth: List[TimeSeriesMetric]
    job_postings: List[TimeSeriesMetric]
    job_completions: List[TimeSeriesMetric]
    payment_volume: List[TimeSeriesMetric]
    active_users: List[TimeSeriesMetric]
    disputes: List[TimeSeriesMetric]

class ModeratedContent(BaseModel):
    id: int
    content_type: ContentType
    content_id: int
    content_preview: str
    reporter_id: Optional[int]
    reporter_name: Optional[str]
    reason: str
    status: str
    created_at: datetime
    moderated_at: Optional[datetime]
    moderator_id: Optional[int]
    moderator_name: Optional[str]
    action_taken: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True

# Revenue Schemas
class WalletFundingRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to fund wallet with")

class SubscriptionRequest(BaseModel):
    """Request to start a subscription"""
    pass  # No additional fields needed, uses fixed price

class EscrowTransactionBase(BaseModel):
    job_id: int
    amount: float = Field(..., gt=0)

class EscrowTransactionCreate(EscrowTransactionBase):
    employer_id: int
    worker_id: int
    commission: float = Field(..., ge=0)

class EscrowTransactionUpdate(BaseModel):
    status: Optional[EscrowStatus]
    admin_notes: Optional[str]

class EscrowTransactionInDB(EscrowTransactionBase):
    id: int
    employer_id: int
    worker_id: int
    commission: float
    status: EscrowStatus
    payment_id: Optional[int]
    release_payment_id: Optional[int]
    admin_notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class RevenueStats(BaseModel):
    """Admin revenue dashboard statistics"""
    total_subscriptions: int
    active_subscriptions: int
    total_application_fees: float
    total_escrow_commission: float
    total_revenue: float
    pending_escrow_amount: float


class PaystackWebhookData(BaseModel):
    """Paystack webhook payload schema"""
    event: str
    data: dict

class AdminRevenueOverview(BaseModel):
    """Admin dashboard revenue overview"""
    stats: RevenueStats
    recent_payments: List[PaymentInDB]
    pending_escrow: List[EscrowTransactionInDB]
    expiring_subscriptions: List[UserInDB]

class DateRangeParams(BaseModel):
    """Query parameters for date-based filtering"""
    start_date: Optional[datetime]
    end_date: Optional[datetime]

class AdminEscrowAction(BaseModel):
    """Admin action on escrow transaction"""
    action: str  # "release" or "hold"
    notes: Optional[str]

class DashboardData(BaseModel):
    # Platform Health & Safety
    flagged_content_reports: int = 0
    pending_moderation_queue: int = 0
    unverified_user_accounts: int = 0
    open_support_tickets: int = 0

    # Daily Operations
    new_user_registrations_today: int = 0
    job_postings_pending_approval: int = 0
    payment_disputes: int = 0
    user_bans_suspensions: int = 0

    # Revenue Monitoring
    daily_revenue: float = 0.0
    weekly_revenue: float = 0.0
    failed_payments: int = 0
    refund_requests: int = 0

    # Quality Control
    application_success_rate: float = 0.0

    # Key Performance Indicators
    active_job_listings: int = 0
    user_engagement_trends: float = 0.0
    conversion_rates: float = 0.0
    
    # Existing useful stats
    total_users: int
    platform_earnings: float
    user_growth_rate: float
    total_payment_volume: float
    total_transactions: int

class AdminUser(BaseModel):
    id: int
    email: str
    phone: Optional[str]
    first_name: str
    last_name: str
    role: str
    is_active: bool
    is_verified: bool
    avatar_url: Optional[str]
    reputation_score: int
    wallet_balance: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserAnalytics(BaseModel):
    total_users: int
    total_workers: int
    total_employers: int
    new_users_last_30_days: int
    user_growth_percentage: float
    weekly_user_growth: List[Dict[str, Any]]

class JobAnalytics(BaseModel):
    total_jobs: int
    open_jobs: int
    completed_jobs: int
    disputed_jobs: int
    job_completion_rate: float
    avg_completion_time_days: float
    top_categories: List[Dict[str, Any]]

class TopUser(BaseModel):
    id: int
    name: str
    total: float

class FinancialAnalytics(BaseModel):
    total_platform_revenue: float
    revenue_last_30_days: float
    total_transaction_volume: float
    avg_transaction_value: float
    weekly_revenue_trend: List[Dict[str, Any]]
    top_earning_workers: List[TopUser]
    top_spending_employers: List[TopUser]

class EngagementAnalytics(BaseModel):
    user_satisfaction_rate: float
    avg_review_rating: float
    disputes_opened_last_30_days: int
    disputes_resolved_last_30_days: int

class PerformanceMetrics(BaseModel):
    platform_uptime: float
    avg_api_response_time_ms: int

class AnalyticsData(BaseModel):
    user_analytics: UserAnalytics
    job_analytics: JobAnalytics
    financial_analytics: FinancialAnalytics
    engagement_analytics: EngagementAnalytics
    performance_metrics: PerformanceMetrics


class AdminTransaction(BaseModel):
    id: int
    user_id: int
    initiator: Optional[UserSimple]
    employer: Optional[UserSimple] = None
    worker: Optional[UserSimple] = None
    amount: float
    fee: Optional[float] = 0
    netAmount: Optional[float] = 0
    type: str
    status: str
    reference: Optional[str] = None
    description: str
    method: Optional[str] = "N/A"
    created_at: datetime
    updated_at: Optional[datetime] = None
    timestamp: datetime
    direction: str

    class Config:
        from_attributes = True


class TransactionList(PaginatedResponse):
    transactions: List[AdminTransaction]


ContentModerationList.model_rebuild()


# ====== New Admin User Management Schemas ======

class UserStatsResponse(BaseModel):
    jobs_posted: int
    jobs_applied: int
    services_posted: int
    reviews_received: int
    disputes_count: int
    profile_completion: float

    class Config:
        from_attributes = True


class KYCSubmissionData(BaseModel):
    id: int
    status: str
    document_type: str
    created_at: Optional[str]
    verified_at: Optional[str]

    class Config:
        from_attributes = True


class CompleteUserView(BaseModel):
    id: int
    email: str
    phone: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    role: str
    is_active: bool
    is_verified: bool
    is_email_verified: bool
    is_kyc_verified: bool
    kyc_status: str
    avatar_url: Optional[str]
    reputation_score: float
    wallet_balance: float
    subscription_status: bool
    subscription_expiry: Optional[str]
    is_2fa_enabled: bool
    failed_login_attempts: int
    lockout_until: Optional[str]
    headline: Optional[str]
    location: Optional[str]
    about_me: Optional[str]
    skills: Optional[List[str]]
    experience_level: Optional[str]
    stats: UserStatsResponse
    kyc: Optional[KYCSubmissionData]
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class ActivityTimelineEntry(BaseModel):
    id: int
    activity_type: str
    description: str
    related_entity_type: Optional[str]
    related_entity_id: Optional[int]
    timestamp: Optional[str]
    activity_data: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True


class ActivityTimelineResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[ActivityTimelineEntry]


class FileData(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_path: str
    file_type: str
    file_size: int
    category: str
    reference_id: Optional[int]
    reference_type: Optional[str]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class FilesByTypeResponse(BaseModel):
    files_by_category: Dict[str, List[FileData]]
    total_files: int


class WithdrawalBankAccount(BaseModel):
    account_number: Optional[str]
    bank_name: Optional[str]
    account_name: Optional[str]


class WithdrawalRequestData(BaseModel):
    id: int
    user_id: int
    amount: float
    tax_amount: float
    total_amount: float
    tax_preference: str
    status: str
    bank_account: Optional[WithdrawalBankAccount]
    admin_notes: Optional[str]
    created_at: Optional[str]
    approved_at: Optional[str]

    class Config:
        from_attributes = True


class WithdrawalRequestsResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[WithdrawalRequestData]


class DisputeDataResponse(BaseModel):
    id: int
    dispute_type: str
    status: str
    claimant_id: Optional[int]
    defendant_id: Optional[int]
    reason: str
    evidence_url: Optional[str] = None
    resolution: Optional[str]
    created_at: Optional[str]
    resolved_at: Optional[str]

    class Config:
        from_attributes = True


class DisputesForUserResponse(BaseModel):
    total: int
    disputes: List[DisputeDataResponse]


class JobPostedData(BaseModel):
    id: int
    title: str
    status: str
    job_price: Optional[float] = None
    budget: Optional[float] = None  # legacy alias
    created_at: Optional[str]

    class Config:
        from_attributes = True


class JobAppliedData(BaseModel):
    id: int
    job_id: int
    job_title: str
    status: str
    applied_at: Optional[str]

    class Config:
        from_attributes = True


class UserJobsResponse(BaseModel):
    jobs_posted: List[JobPostedData]
    jobs_applied: List[JobAppliedData]


class ServiceData(BaseModel):
    id: int
    title: str
    description: str
    category: str
    price: float
    delivery_days: int
    revisions: int
    created_at: Optional[str]

    class Config:
        from_attributes = True


class UserServicesResponse(BaseModel):
    total: int
    services: List[ServiceData]


class ReviewData(BaseModel):
    id: int
    rating: int
    comment: str
    reviewee_id: Optional[int]
    reviewer_id: Optional[int]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class UserReviewsResponse(BaseModel):
    reviews_given: List[ReviewData]
    reviews_received: List[ReviewData]
    average_rating: float


class UserProfileUpdateRequest(BaseModel):
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    avatar_url: Optional[str]
    location: Optional[str]
    headline: Optional[str]
    about_me: Optional[str]
    skills: Optional[List[str]]
    experience_level: Optional[str]


class AccountStatusChangeRequest(BaseModel):
    status: str  # "active", "suspended", "banned"
    reason: Optional[str]
    duration_days: Optional[int]


class WalletOperationRequest(BaseModel):
    amount: float
    description: str


class SubscriptionChangeRequest(BaseModel):
    plan_id: int
    duration_months: Optional[int]


class AuthResetRequest(BaseModel):
    reset_password: bool = False
    reset_2fa: bool = False
    clear_login_attempts: bool = False


class RoleSwitchRequest(BaseModel):
    new_role: str  # "WORKER" or "EMPLOYER"


class AdminAuditLogSchema(BaseModel):
    id: int
    admin_id: int
    action_type: str
    target_user_id: Optional[int]
    target_entity_type: Optional[str]
    target_entity_id: Optional[int]
    description: Optional[str]
    old_values: Optional[Dict[str, Any]]
    new_values: Optional[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class AdminAuditLogsResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[AdminAuditLogSchema]


# ====== KYC Admin Management Schemas ======

class KYCUserInfo(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    phone: str


class KYCSubmissionDetailResponse(BaseModel):
    id: int
    user_id: int
    user: Optional[KYCUserInfo]
    document_type: str
    document_path: str
    selfie_path: str
    status: str
    notes: Optional[str]
    created_at: Optional[str]
    verified_at: Optional[str]

    class Config:
        from_attributes = True


class KYCApprovalRequest(BaseModel):
    notes: Optional[str]


class KYCRejectionRequest(BaseModel):
    reason: str
    notes: Optional[str]


class KYCResubmissionRequest(BaseModel):
    reason: str
    notes: Optional[str]


# ====== Withdrawal Admin Management Schemas ======

class WithdrawalUserInfo(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    phone: str


class WithdrawalBankAccountDetail(BaseModel):
    id: int
    account_number: str
    bank_name: str
    account_name: str
    is_primary: bool


class WithdrawalApprovedByInfo(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str


class WithdrawalRequestDetailResponse(BaseModel):
    id: int
    user_id: int
    user: Optional[WithdrawalUserInfo]
    amount: float
    tax_amount: float
    total_amount: float
    tax_preference: str
    status: str
    bank_account: Optional[WithdrawalBankAccountDetail]
    admin_notes: Optional[str]
    payment_id: Optional[int]
    created_at: Optional[str]
    approved_at: Optional[str]
    approved_by: Optional[WithdrawalApprovedByInfo]

    class Config:
        from_attributes = True


class WithdrawalApprovalRequest(BaseModel):
    notes: Optional[str]


class WithdrawalRejectionRequest(BaseModel):
    reason: str
    notes: Optional[str]


class WithdrawalNotesRequest(BaseModel):
    notes: str
