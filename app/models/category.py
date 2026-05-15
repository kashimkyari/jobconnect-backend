from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.db.base_class import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)

    # Note: Job model uses string-based category_id (e.g., 'healthcare', 'cleaning') without foreign keys
    # Only Service model has a proper ForeignKey relationship to Category
    services = relationship("Service", back_populates="category")
