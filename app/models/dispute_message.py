from sqlalchemy import Column, Integer, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

class DisputeMessage(Base):
    """
    Model for tracking messages and evidence inside a dispute.
    """
    __tablename__ = "dispute_messages"

    id = Column(Integer, primary_key=True, index=True)
    dispute_id = Column(Integer, ForeignKey("disputes.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    message = Column(Text, nullable=False)
    is_admin_reply = Column(Boolean, default=False)
    
    # Optional evidence link (could be S3 URL or local path)
    evidence_url = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    dispute = relationship("Dispute", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id])
    attachments = relationship("DisputeAttachment", back_populates="message", cascade="all, delete-orphan", lazy="selectin")
