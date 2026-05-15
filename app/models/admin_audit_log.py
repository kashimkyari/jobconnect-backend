from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Text, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base


class AdminActionType(str, enum.Enum):
    """Types of admin actions that can be performed"""
    ACCOUNT_STATUS_CHANGE = "account_status_change"  # suspend/ban/reactivate
    PROFILE_UPDATE = "profile_update"
    WALLET_ADD_FUNDS = "wallet_add_funds"
    WALLET_DEDUCT_FUNDS = "wallet_deduct_funds"
    SUBSCRIPTION_CHANGE = "subscription_change"
    AUTHENTICATION_RESET = "authentication_reset"
    ROLE_SWITCH = "role_switch"
    KYC_APPROVED = "kyc_approved"
    KYC_REJECTED = "kyc_rejected"
    KYC_RESUBMISSION_REQUESTED = "kyc_resubmission_requested"
    WITHDRAWAL_APPROVED = "withdrawal_approved"
    WITHDRAWAL_REJECTED = "withdrawal_rejected"
    WITHDRAWAL_RETRIED = "withdrawal_retried"
    DISPUTE_RESOLVED = "dispute_resolved"
    USER_VERIFIED = "user_verified"
    CONTENT_MODERATED = "content_moderated"


class AdminAuditLog(Base):
    """
    Tracks all admin actions performed on users and system entities.
    Provides complete audit trail for compliance and accountability.
    """
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action_type = Column(Enum(AdminActionType), nullable=False, index=True)
    
    # The user/entity affected by this action
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    target_entity_type = Column(String, nullable=True)  # e.g., "withdrawal_request", "kyc_submission", "dispute"
    target_entity_id = Column(Integer, nullable=True)
    
    # Action details
    description = Column(Text, nullable=True)  # Human-readable summary
    old_values = Column(JSON, nullable=True)  # Old state before change
    new_values = Column(JSON, nullable=True)  # New state after change
    context_data = Column(JSON, nullable=True)  # Additional context
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    admin = relationship("User", foreign_keys=[admin_id], back_populates="admin_actions")
    target_user = relationship("User", foreign_keys=[target_user_id], back_populates="audit_logs_targeting_user")
    
    def __repr__(self):
        return f"<AdminAuditLog(id={self.id}, admin_id={self.admin_id}, action_type={self.action_type}, target_user_id={self.target_user_id})>"
