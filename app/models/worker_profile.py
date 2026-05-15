from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class RecentWork(Base):
    __tablename__ = "recent_work"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    image_url = Column(String, nullable=False)

    user = relationship("User", back_populates="recent_works")

class UserService(Base):
    __tablename__ = "user_services"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    service_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    user = relationship("User", back_populates="services_offered")
