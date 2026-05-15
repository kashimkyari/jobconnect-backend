from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
    func,
)
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class ExpoPushReceipt(Base):
    __tablename__ = "expo_push_receipts"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(String, nullable=False, unique=True, index=True)
    source_type = Column(String, nullable=False, server_default=text("'transactional'"), index=True)
    status = Column(String, nullable=False, server_default=text("'sent'"), index=True)
    expo_push_token = Column(String, nullable=False, index=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    push_device_id = Column(Integer, ForeignKey("push_devices.id", ondelete="SET NULL"), nullable=True, index=True)
    notification_id = Column(Integer, ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True, index=True)
    admin_log_id = Column(Integer, ForeignKey("push_notification_logs.id", ondelete="SET NULL"), nullable=True, index=True)

    error_code = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User")
    push_device = relationship("PushDevice", back_populates="receipts")
    notification = relationship("Notification")
    admin_log = relationship("PushNotificationLog")
