from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Enum as SQLEnum, text
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

from app.db.base_class import Base
from app.schemas.message import MessageType

class Message(Base, AsyncAttrs):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(String, nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True, index=True)
    application_id = Column(Integer, ForeignKey("job_applications.id"), nullable=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True, index=True)
    message_type = Column(SQLEnum(MessageType), default=MessageType.TEXT, nullable=False)
    call_type = Column(String, nullable=True)
    call_duration = Column(Integer, nullable=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=True, index=True)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'), nullable=False, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text('CURRENT_TIMESTAMP'),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    sender = relationship("User", back_populates="sent_messages", foreign_keys=[sender_id], lazy="selectin")
    receiver = relationship("User", back_populates="received_messages", foreign_keys=[receiver_id], lazy="selectin")
    file = relationship("File", lazy="joined")
    job = relationship("Job", lazy="joined")
    application = relationship("JobApplication", lazy="joined")
    booking = relationship("Booking", back_populates="messages", lazy="joined")
