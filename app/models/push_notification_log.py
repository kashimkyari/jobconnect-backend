from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, text, func
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from datetime import datetime
import enum


class PushDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    FAILED = "failed"
    NOT_SENT = "not_sent"  # User has push notifications disabled


class PushNotificationLog(Base):
    __tablename__ = "push_notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    delivery_status = Column(
        Enum(PushDeliveryStatus),
        nullable=False,
        default=PushDeliveryStatus.PENDING,
        index=True
    )
    failure_reason = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
        index=True
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    admin = relationship("User", foreign_keys=[admin_id])
    user = relationship("User", foreign_keys=[user_id])
