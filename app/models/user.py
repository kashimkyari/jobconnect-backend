from sqlalchemy import Column, Integer, String, Enum, Float, Boolean, DateTime, ForeignKey, text, Text, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.models.enums import UserRole
from app.models.bank_account import BankAccount
from app.models.worker_profile import RecentWork
from .notification_settings import NotificationSettings
from .profile_view import ProfileView

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    role = Column(Enum(UserRole), nullable=True, index=True)  # nullable for new OAuth users before role selection
    is_active = Column(Boolean, default=True, index=True)
    is_verified = Column(Boolean, default=False, index=True)
    is_kyc_verified = Column(Boolean, default=False, index=True)
    kyc_status = Column(String, default="not_started", index=True)
    is_onboarding_complete = Column(Boolean, default=False, index=True)
    onboarding_step = Column(Integer, default=0)
    avatar_url = Column(String)
    reputation_score = Column(Float, default=0.0)
    wallet_balance = Column(Numeric(10, 2), default=0.0)
    free_applications_used = Column(Integer, default=0)
    free_job_posts_used = Column(Integer, default=0)
    remaining_job_posts = Column(Integer, default=0)
    remaining_job_applications = Column(Integer, default=0)
    unsuccessful_applications_streak = Column(Integer, default=0)
    subscription_status = Column(Boolean, default=False)
    subscription_expiry = Column(DateTime(timezone=True))
    subscription_paystack_id = Column(String)
    subscription_plan_id = Column(Integer, ForeignKey("subscription_plans.id"), index=True)
    paystack_customer_code = Column(String, nullable=True)
    
    # Security fields
    hashed_transaction_pin = Column(String, nullable=True)
    is_2fa_enabled = Column(Boolean, default=False)
    otp_secret = Column(String, nullable=True)

    # OAuth fields
    oauth_provider = Column(String, nullable=True, index=True)  # 'google', 'apple', etc.
    oauth_id = Column(String, nullable=True, index=True)  # Provider's user ID
    is_email_verified = Column(Boolean, default=False)  # Email verification status

    failed_login_attempts = Column(Integer, default=0)
    lockout_until = Column(DateTime(timezone=True), nullable=True)
    
    # Streak tracking
    streak_count = Column(Integer, default=0)
    last_streak_claim_at = Column(DateTime(timezone=True), nullable=True)
    
    # Push Notifications
    expo_push_token = Column(String, nullable=True, index=True)
    push_notifications_enabled = Column(Boolean, default=True, index=True)
    # Track user's recent activity to approximate presence for push delivery
    last_active_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now(), nullable=False)

    @property
    def average_rating(self):
        """Alias for reputation_score for backward compatibility."""
        return self.reputation_score
    
    @average_rating.setter
    def average_rating(self, value):
        """Allow setting average_rating as an alias of reputation_score."""
        self.reputation_score = value

    # Relationships
    # Job-related relationships
    jobs_posted = relationship("Job", foreign_keys="[Job.employer_id]", back_populates="employer")
    jobs_worked = relationship("Job", foreign_keys="[Job.worker_id]", back_populates="worker")
    jobs_applied = relationship("JobApplication", back_populates="worker")
    
    # Service relationships
    services = relationship("Service", back_populates="worker")
    
    # Booking relationships
    bookings_created = relationship("Booking", foreign_keys="[Booking.employer_id]", back_populates="employer", lazy="dynamic")
    bookings_received = relationship("Booking", foreign_keys="[Booking.worker_id]", back_populates="worker", lazy="dynamic")
    
    # File relationships
    files = relationship("File", back_populates="user")
    
    # Review relationships (using strings to avoid circular imports)
    reviews_given = relationship(
        "Review",
        foreign_keys="[Review.reviewer_id]",
        back_populates="reviewer",
        lazy="dynamic"
    )
    reviews_received = relationship(
        "Review",
        foreign_keys="[Review.reviewee_id]",
        back_populates="reviewee"
    )
    
    # Other relationships
    sent_messages = relationship(
        "Message",
        foreign_keys="[Message.sender_id]",
        back_populates="sender",
        lazy="dynamic"
    )
    received_messages = relationship(
        "Message",
        foreign_keys="[Message.receiver_id]",
        back_populates="receiver",
        lazy="dynamic"
    )
    
    # Verification and payment relationships
    kyc_submissions = relationship("KYCSubmission", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    bank_accounts = relationship("BankAccount", back_populates="user")
    withdrawal_requests = relationship("WithdrawalRequest", foreign_keys="[WithdrawalRequest.user_id]", back_populates="user")
    
    # Badge relationships
    earned_badges = relationship("UserBadge", back_populates="user", lazy="dynamic")
    
    # Escrow relationships
    employer_escrows = relationship(
        "EscrowTransaction",
        foreign_keys="[EscrowTransaction.employer_id]",
        back_populates="employer",
        lazy="dynamic"
    )
    worker_escrows = relationship(
        "EscrowTransaction",
        foreign_keys="[EscrowTransaction.worker_id]",
        back_populates="worker",
        lazy="dynamic"
    )
    
    # Dispute relationships
    disputes_claimed = relationship(
        "Dispute",
        foreign_keys="[Dispute.claimant_id]",
        back_populates="claimant",
        lazy="dynamic"
    )
    disputes_defended = relationship(
        "Dispute",
        foreign_keys="[Dispute.defendant_id]",
        back_populates="defendant",
        lazy="dynamic"
    )
    disputes_resolved = relationship(
        "Dispute",
        foreign_keys="[Dispute.resolved_by_admin_id]",
        back_populates="resolved_by_admin",
        lazy="dynamic"
    )
    withdrawal_disputes = relationship(
        "Dispute",
        foreign_keys="[Dispute.user_id]",
        back_populates="affected_user",
        lazy="dynamic"
    )

    notifications = relationship("Notification", back_populates="user", lazy="dynamic")
    subscription_plan = relationship("SubscriptionPlan", back_populates="users")

    # Referral fields
    referred_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    referral_code = Column(String, unique=True, index=True)
    rewards = relationship("Reward", back_populates="user")

    # Worker-specific profile information
    headline = Column(String, nullable=True)
    location = Column(String)
    about_me = Column(Text)
    service_category = Column(String)  # To see jobs from this category first
    skills = Column(JSONB, nullable=True)  # Array of skill strings
    experience_level = Column(String)  # beginner, intermediate, advanced, expert
    id_type = Column(String)
    id_number = Column(String)
    id_image_url = Column(String)
    selfie_image_url = Column(String)
    
    # Location-based matching fields
    latitude = Column(Float, nullable=True)  # GPS latitude coordinate
    longitude = Column(Float, nullable=True)  # GPS longitude coordinate
    city = Column(String, nullable=True)  # City name
    state = Column(String, nullable=True)  # State/Province
    country = Column(String, nullable=True)  # Country name
    search_radius_km = Column(Integer, server_default=text("50"), default=50)  # Preferred search radius for location-based matching
    
    # Worker availability - JSON array format: [{"day": "monday", "slots": ["9:00 AM", "2:00 PM"]}, ...]
    worker_availability = Column(JSONB, nullable=True, default=[])  # Availability schedule for stories/services

    # Relationships to worker profile models
    recent_works = relationship("RecentWork", back_populates="user", lazy="selectin", cascade="all, delete-orphan")
    services_offered = relationship("UserService", back_populates="user", lazy="selectin", cascade="all, delete-orphan")
    services = relationship("Service", back_populates="worker", cascade="all, delete-orphan")
    stories = relationship("Story", back_populates="worker", cascade="all, delete-orphan", lazy="dynamic")
    recent_activities = relationship("RecentActivity", back_populates="user", lazy="dynamic")
    
    # Profile views relationships
    profile_views_received = relationship(
        "ProfileView",
        foreign_keys="[ProfileView.user_id]",
        back_populates="user",
        lazy="dynamic"
    )

    notification_settings = relationship("NotificationSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    push_devices = relationship(
        "PushDevice",
        foreign_keys="[PushDevice.user_id]",
        back_populates="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    
    # Push notification logs (notifications sent by admin to this user)
    push_notification_logs = relationship(
        "PushNotificationLog",
        foreign_keys="[PushNotificationLog.user_id]",
        back_populates="user",
        lazy="dynamic"
    )
    
    # Admin audit log relationships
    admin_actions = relationship(
        "AdminAuditLog",
        foreign_keys="[AdminAuditLog.admin_id]",
        back_populates="admin",
        lazy="dynamic"
    )
    audit_logs_targeting_user = relationship(
        "AdminAuditLog",
        foreign_keys="[AdminAuditLog.target_user_id]",
        back_populates="target_user",
        lazy="dynamic"
    )
