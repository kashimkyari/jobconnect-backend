from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text, Boolean, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta, timezone
import enum

from app.db.base_class import Base


class MediaType(str, enum.Enum):
    """Media type for stories"""
    IMAGE = "image"
    VIDEO = "video"


class Story(Base):
    """
    Represents a short-lived story from a worker showcasing their service.
    Stories expire after 3 days and are soft-deleted via is_active flag.
    """
    __tablename__ = "stories"

    id = Column(Integer, primary_key=True, index=True)

    # Core relationships
    worker_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("services.id", ondelete="SET NULL"), nullable=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)

    # Media
    media_url = Column(String, nullable=False)  # File path from FileService
    media_type = Column(SQLEnum(MediaType), default=MediaType.IMAGE, nullable=False)
    thumbnail_url = Column(String, nullable=True)  # For videos, first frame

    # Metadata
    caption = Column(Text, nullable=True)
    
    # Denormalized service data (for speed, avoid joins)
    service_name = Column(String, nullable=False)
    service_desc = Column(Text, nullable=True)
    price = Column(Float, nullable=True)
    duration = Column(Integer, nullable=True)  # in days

    # Denormalized worker availability (JSON format)
    # Format: [{"day": "monday", "slots": ["9:00 AM", "2:00 PM"]}, ...]
    worker_availability = Column(JSONB, default=[], nullable=True)

    # Lifecycle
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    view_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    worker = relationship("User", back_populates="stories", lazy="selectin")
    service = relationship("Service", lazy="selectin")
    job = relationship("Job", lazy="selectin")
    views = relationship("StoryView", back_populates="story", cascade="all, delete-orphan", lazy="selectin")

    @classmethod
    def calculate_expiry(cls):
        """Calculate expiry timestamp (3 days from now)"""
        return datetime.now(timezone.utc) + timedelta(days=3)


class StoryView(Base):
    """
    Tracks which users have viewed which stories.
    Used for seen/unseen status and view count analytics.
    """
    __tablename__ = "story_views"

    id = Column(Integer, primary_key=True, index=True)

    # Core relationships
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    viewer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Timestamp
    viewed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    story = relationship("Story", back_populates="views")
    viewer = relationship("User", lazy="selectin")

    # Unique constraint to prevent duplicate views
    __table_args__ = (
        UniqueConstraint('story_id', 'viewer_id', name='uq_story_viewer'),
    )

    class Config:
        from_attributes = True
