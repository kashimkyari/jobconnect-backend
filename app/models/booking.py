from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, Text, Enum as SQLEnum, JSON, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from datetime import datetime, timedelta

from app.db.base_class import Base
from app.models.enums import BookingStatus
from app.models.payment import PaymentStatus

class Booking(Base):
    """
    Represents a service booking request from an employer to a worker.
    Tracks the complete lifecycle of service hiring from request to completion.
    """
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    
    # Core relationships
    service_id = Column(Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True)
    employer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    worker_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Booking details
    status = Column(
        SQLEnum(
            BookingStatus,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            native_enum=True,
        ),
        default=BookingStatus.BOOKED,
        index=True,
        nullable=False,
    )
    
    # Schedule information
    start_date = Column(DateTime(timezone=True), nullable=False, index=True)
    start_time = Column(Time, nullable=True)
    duration_hours = Column(Integer, nullable=False)  # Duration in hours
    estimated_end_date = Column(DateTime(timezone=True), nullable=True)  # Calculated end date

    # Location (employer address)
    address = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # Pricing
    hourly_rate = Column(Float, nullable=False)  # Rate at time of booking
    total_price = Column(Float, nullable=False)
    
    # Payment tracking
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True, index=True)
    payment_status = Column(SQLEnum(PaymentStatus), nullable=True)
    
    # Communication
    message = Column(Text, nullable=True)  # Employer's message/requirements for the booking
    worker_notes = Column(Text, nullable=True)  # Worker's notes when accepting/rejecting
    
    # Employer review/rating for this specific booking
    employer_review = Column(Text, nullable=True)  # Review text from employer
    employer_rating = Column(Float, nullable=True)  # Rating (1-5) from employer
    
    # Additional metadata (using booking_metadata to avoid SQLAlchemy reserved name)
    booking_metadata = Column(JSONB, nullable=True)  # Flexible storage for additional booking data
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)  # When worker accepted
    rejected_at = Column(DateTime(timezone=True), nullable=True)  # When worker rejected
    cancelled_at = Column(DateTime(timezone=True), nullable=True)  # When booking was cancelled
    completed_at = Column(DateTime(timezone=True), nullable=True)  # When service was completed
    
    # Relationships
    service = relationship("Service", lazy="selectin")
    employer = relationship("User", foreign_keys=[employer_id], lazy="selectin", back_populates="bookings_created")
    worker = relationship("User", foreign_keys=[worker_id], lazy="selectin", back_populates="bookings_received")
    payment = relationship("Payment", lazy="joined")
    messages = relationship("Message", back_populates="booking", cascade="all, delete-orphan")
    
    def calculate_estimated_end_date(self):
        """Calculate estimated end date based on start date and duration"""
        return self.start_date + timedelta(hours=self.duration_hours)
