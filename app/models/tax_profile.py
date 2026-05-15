from sqlalchemy import Column, Integer, String, Enum, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from enum import Enum as PyEnum

from app.db.base_class import Base


class TaxProfileState(str, PyEnum):
    """Tax profile states"""
    NOT_REGISTERED = "not_registered"
    REGISTERED = "registered"  # TIN provided but not verified
    PENDING_VERIFICATION = "pending_verification"  # Verification in progress
    VERIFIED = "verified"  # Verified and compliant
    TAX_EXEMPT = "tax_exempt"  # Exempt from tax
    SUSPENDED = "suspended"  # Suspended for non-compliance


class WorkerTaxProfile(Base):
    __tablename__ = "worker_tax_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True, nullable=False)
    
    # Tax identification
    tin = Column(String, unique=True, index=True, nullable=False)
    bvn = Column(String, unique=True, index=True, nullable=True)
    
    # Tax classification
    tax_classification = Column(String, default="individual", nullable=False)  # individual, business, etc.
    
    # State tracking
    state = Column(Enum(TaxProfileState), default=TaxProfileState.REGISTERED, index=True, nullable=False)
    is_verified = Column(Boolean, default=False, index=True)
    is_tax_exempt = Column(Boolean, default=False)
    
    # Verification details
    verification_status = Column(String, default="pending")  # pending, approved, rejected
    verification_notes = Column(Text, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by_admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Compliance tracking
    last_filing_date = Column(DateTime(timezone=True), nullable=True)
    next_filing_due = Column(DateTime(timezone=True), nullable=True)
    is_compliant = Column(Boolean, default=True)
    compliance_warnings = Column(Integer, default=0)
    
    # Metadata
    additional_info = Column(JSONB, nullable=True)  # For storing extra tax info
    
    # Timestamps
    registered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="tax_profile")
    verified_by_admin = relationship(
        "User",
        foreign_keys=[verified_by_admin_id],
        backref="verified_tax_profiles"
    )

    def __repr__(self):
        return f"<WorkerTaxProfile(user_id={self.user_id}, state={self.state}, is_verified={self.is_verified})>"
