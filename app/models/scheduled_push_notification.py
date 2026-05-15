from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base


class ScheduledPushStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"


class ScheduledPushNotification(Base):
    __tablename__ = "scheduled_push_notifications"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    filters = Column(JSONB, nullable=False, default=dict)
    scheduled_time = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(Enum(ScheduledPushStatus), nullable=False, default=ScheduledPushStatus.SCHEDULED, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    admin = relationship("User", foreign_keys=[admin_id])
