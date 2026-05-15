from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base_class import Base

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), index=True)
    reviewee_id = Column(Integer, ForeignKey("users.id"), index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), index=True, nullable=True)
    service_id = Column(Integer, ForeignKey("services.id"), index=True, nullable=True)
    rating = Column(Float, nullable=False, index=True)  # 1-5 stars
    comment = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    reviewer = relationship(
        "User",
        foreign_keys=[reviewer_id],
        back_populates="reviews_given"
    )
    reviewee = relationship(
        "User",
        foreign_keys=[reviewee_id],
        back_populates="reviews_received"
    )
    job = relationship("Job", back_populates="reviews")
    service = relationship("Service", back_populates="reviews")
