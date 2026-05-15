from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from datetime import datetime
import enum

class NotificationCategory(str, enum.Enum):
    JOBS_AND_MATCHES = "jobs_and_matches"
    BOOKING = "bookings"
    BOOKINGS = "bookings"
    MESSAGES = "messages"
    PAYMENTS_AND_WALLET = "payments_and_wallet"
    DEADLINES_AND_ACTIONS_REQUIRED = "deadlines_and_actions_required"
    TRUST_AND_SAFETY = "trust_and_safety"
    REVIEWS_AND_REPUTATION = "reviews_and_reputation"
    KYC_AND_VERIFICATION = "kyc_and_verification"
    PLATFORM_UPDATES = "platform_updates"
    PROFILE_VIEW = "profile_view"

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, index=True, nullable=False)
    message = Column(String, index=True, nullable=False)
    read = Column(Boolean, default=False, nullable=False)
    category = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # For action-driven notifications
    action_screen = Column(String, nullable=True)  # e.g., "JobDetails", "Chat"
    action_payload = Column(JSON, nullable=True)  # e.g., {"job_id": 123}, {"chat_id": 456}

    user = relationship("User", back_populates="notifications")
