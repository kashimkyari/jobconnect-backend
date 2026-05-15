from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum, and_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, foreign
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base
from .file import File

class JobStatus(str, enum.Enum):
    """Core job statuses - simplified from 7 to 4 core statuses"""
    DRAFT = "draft"          # Job created but not published
    OPEN = "open"            # Job published and accepting applications
    IN_PROGRESS = "in_progress"  # Worker hired and working
    COMPLETED = "completed"  # Work finished and paid

class CompletionStage(str, enum.Enum):
    """Tracks the stage of job completion"""
    NOT_STARTED = "not_started"           # Job in progress, no completion initiated
    AWAITING_WORKER = "awaiting_worker"   # Waiting for worker to mark complete
    AWAITING_PAYMENT = "awaiting_payment" # Worker completed, processing payment
    PAID = "paid"                          # Payment completed

class JobLocationType(str, enum.Enum):
    REMOTE = "remote"
    ONSITE = "onsite"
    HYBRID = "hybrid"

class JobType(str, enum.Enum):
    ONE_TIME = "one_time"
    PART_TIME = "part_time"
    FULL_TIME = "full_time"

class ExperienceLevel(str, enum.Enum):
    ENTRY = "entry"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"

class PaymentType(str, enum.Enum):
    FIXED_PRICE = "fixed_price"
    HOURLY_RATE = "hourly_rate"

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(String, nullable=False)
    experience_level = Column(Enum(ExperienceLevel), nullable=True)
    payment_type = Column(Enum(PaymentType), nullable=True)
    hourly_rate = Column(Float, nullable=True)
    estimated_hours = Column(Integer, nullable=True)
    country = Column(String, index=True)
    city = Column(String, index=True)
    latitude = Column(Float, nullable=True)  # GPS latitude coordinate
    longitude = Column(Float, nullable=True)  # GPS longitude coordinate
    job_price = Column(Float, nullable=True)  # Fixed price for the job (required for fixed_price payment type)
    confirmed_price = Column(Float, nullable=True)  # Final negotiated price after hiring
    location_type = Column(Enum(JobLocationType), nullable=False, index=True)
    job_type = Column(Enum(JobType), nullable=True, index=True)
    tags = Column(JSONB, nullable=True)
    status = Column(Enum(JobStatus), default=JobStatus.DRAFT, index=True)
    is_archived = Column(Boolean, default=False, index=True)  # Soft-delete flag instead of ARCHIVED status
    employer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    worker_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    category_id = Column(String(50), nullable=True, index=True)  # Client-side category ID (e.g., 'healthcare', 'cleaning')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Revenue-related fields
    is_high_value = Column(Boolean, default=False)  # Determines if escrow is required
    escrow_required = Column(Boolean, default=False)
    commission_rate = Column(Float, default=0.10)  # 10% platform fee for high-value jobs
    completed_at = Column(DateTime(timezone=True))
    worker_completed = Column(Boolean, default=False)
    employer_completed = Column(Boolean, default=False)
    hired_at = Column(DateTime(timezone=True))
    contract_details = Column(String, nullable=True)
    
    # Boost feature fields
    boost_active = Column(Boolean, default=False, index=True)  # Whether job is currently boosted
    boost_expires_at = Column(DateTime(timezone=True), nullable=True)  # When boost expires
    
    # Completion lifecycle tracking
    completion_stage = Column(Enum(CompletionStage), default=CompletionStage.NOT_STARTED, index=True)
    
    # Dispute tracking (separate from job status)
    dispute_status = Column(String(50), nullable=True)  # 'DISPUTED', 'RESOLVED', 'CANCELLED', etc.
    
    # Request tracking for idempotency (prevents duplicate operations)
    last_request_id = Column(String(128), nullable=True, unique=False)
    last_request_at = Column(DateTime(timezone=True), nullable=True)
    repeated_from_job_id = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Relationships
    employer = relationship("User", foreign_keys=[employer_id], back_populates="jobs_posted")
    worker = relationship("User", foreign_keys=[worker_id], back_populates="jobs_worked")
    applications = relationship("JobApplication", back_populates="job", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="job")
    escrow_transactions = relationship("EscrowTransaction", back_populates="job")
    reviews = relationship("Review", back_populates="job", cascade="all, delete-orphan", lazy="selectin")
    disputes = relationship("Dispute", back_populates="job")
    attachments = relationship(
        "File",
        primaryjoin=lambda: and_(foreign(File.reference_id) == Job.id, File.reference_type == "job"),
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    repeated_from_job = relationship("Job", remote_side=[id], back_populates="reposted_jobs")
    reposted_jobs = relationship("Job", back_populates="repeated_from_job")

    @hybrid_property
    def location(self):
        if self.location_type == JobLocationType.REMOTE:
            return "Remote"
        
        parts = []
        if self.city:
            parts.append(self.city)
        if self.country:
            parts.append(self.country)
        
        return ", ".join(parts) if parts else None

    def calculate_commission(self) -> float:
        """Calculate the platform commission for this job"""
        return self.job_price * self.commission_rate if self.is_high_value else 0.0
