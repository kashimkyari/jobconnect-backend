from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base
from app.schemas.employer_dashboard import ActivityType

class RecentActivity(Base):
    __tablename__ = "recent_activities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    activity_type = Column(Enum(ActivityType), index=True, nullable=False)
    description = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # To link to related entities, e.g., a job application, a message, a profile view
    related_entity_type = Column(String, nullable=True)
    related_entity_id = Column(Integer, nullable=True)
    
    activity_data = Column(JSON, nullable=True)  # For extra metadata

    user = relationship("User", back_populates="recent_activities")
