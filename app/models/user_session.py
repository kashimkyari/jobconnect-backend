from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base_class import Base

class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_hash = Column(String, nullable=False, unique=True, index=True)
    device_name = Column(String, nullable=True) # e.g. "Vivian's iPhone XS"
    device_model = Column(String, nullable=True) # e.g. "iPhone13,4", "kminilte"
    device_brand = Column(String, nullable=True) # e.g. Apple, Google
    device_type = Column(String, nullable=True) # e.g. mobile, desktop, tablet
    os_name = Column(String, nullable=True) # e.g. iOS, Android
    os_version = Column(String, nullable=True) # e.g. 16.4.1
    ip_address = Column(String, nullable=True)
    location = Column(String, nullable=True) # e.g. "Lagos, Nigeria"
    user_agent = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    is_deleted = Column(Boolean, default=False, index=True)
    last_used_at = Column(DateTime(timezone=True), default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Use string reference to avoid circular imports
    user = relationship("User", backref="sessions")
