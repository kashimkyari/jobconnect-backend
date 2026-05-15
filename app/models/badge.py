from sqlalchemy import Column, Integer, String, Float
from app.db.base_class import Base

class Badge(Base):
    __tablename__ = "badges"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, unique=True, nullable=False)
    description = Column(String, nullable=False)
    icon_url = Column(String, nullable=True)
    criteria_type = Column(String, nullable=False)  # e.g., "rating", "jobs_completed"
    criteria_value = Column(Float, nullable=False)
