from sqlalchemy import (
    Boolean,
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


class PushDevice(Base):
    __tablename__ = "push_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expo_push_token = Column(String, nullable=False, unique=True, index=True)
    provider = Column(String, nullable=False, server_default=text("'expo'"), index=True)
    platform = Column(String, nullable=True)
    device_id = Column(String, nullable=True, index=True)
    app_version = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    invalidated_reason = Column(String, nullable=True)
    last_seen_at = Column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="push_devices")
    receipts = relationship("ExpoPushReceipt", back_populates="push_device", lazy="dynamic")
