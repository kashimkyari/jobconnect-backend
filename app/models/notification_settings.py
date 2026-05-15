from sqlalchemy import Column, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    push_notifications = Column(Boolean, default=True)
    email_notifications = Column(Boolean, default=False)
    job_updates = Column(Boolean, default=True)
    application_updates = Column(Boolean, default=True)
    new_message = Column(Boolean, default=True)

    user = relationship("User", back_populates="notification_settings")
