from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from app.db.base_class import Base

class Waitlist(Base):
    __tablename__ = "waitlist"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    user_type = Column(String, nullable=False)
    location = Column(String, nullable=False)
    newsletter = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
