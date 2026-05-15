from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base

class DisputeAttachment(Base):
    __tablename__ = "dispute_attachments"

    id = Column(Integer, primary_key=True, index=True)
    dispute_id = Column(Integer, ForeignKey("disputes.id", ondelete="CASCADE"), nullable=True, index=True)
    message_id = Column(Integer, ForeignKey("dispute_messages.id", ondelete="CASCADE"), nullable=True, index=True)
    
    file_url = Column(Text, nullable=False)
    file_type = Column(String, nullable=False) # e.g., 'image/jpeg', 'video/mp4'
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    dispute = relationship("Dispute", back_populates="attachments")
    message = relationship("DisputeMessage", back_populates="attachments")
