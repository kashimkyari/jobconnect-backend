from sqlalchemy import Column, Integer, String, ForeignKey, Float, JSON, DateTime
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from app.models.enums import PricingModel
from datetime import datetime

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String)
    price = Column(Float, nullable=False)
    pricing_model = Column(String, default="fixed_price", nullable=False)
    estimated_delivery_time = Column(String)
    revisions = Column(Integer, default=1)
    tags = Column(JSON, default=[])
    
    # Location fields
    city = Column(String, nullable=True)  # e.g., "Lagos", "Abuja"
    country = Column(String, default="Nigeria", nullable=False)
    latitude = Column(Float, nullable=True)  # GPS latitude coordinate
    longitude = Column(Float, nullable=True)  # GPS longitude coordinate
    
    # Use the shared 'categories' table, not 'service_categories'
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    worker_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_request_id = Column(String(128), nullable=True, index=True)
    last_request_at = Column(DateTime, nullable=True)

    category = relationship("Category", back_populates="services")
    worker = relationship("User", back_populates="services")
    reviews = relationship("Review", back_populates="service", cascade="all, delete-orphan")
