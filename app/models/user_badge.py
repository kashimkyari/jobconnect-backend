from sqlalchemy import Column, Integer, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base


class BadgeAwardStatus(str, enum.Enum):
    """Status of badge award"""
    EARNED = "earned"  # User meets criteria
    LOST = "lost"  # User no longer meets criteria


class UserBadge(Base):
    """
    Tracks badges earned by users.
    Records when a user earned a badge (timestamp) and whether they still maintain it.
    """
    __tablename__ = "user_badges"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    badge_id = Column(Integer, ForeignKey("badges.id"), nullable=False, index=True)
    
    # Track badge status and timestamps
    status = Column(Enum(BadgeAwardStatus), default=BadgeAwardStatus.EARNED, nullable=False)
    earned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    lost_at = Column(DateTime(timezone=True), nullable=True)  # When user stopped qualifying
    
    # Relationships
    user = relationship("User", back_populates="earned_badges")
    badge = relationship("Badge")
    
    def __repr__(self):
        return f"<UserBadge(user_id={self.user_id}, badge_id={self.badge_id}, status={self.status})>"
