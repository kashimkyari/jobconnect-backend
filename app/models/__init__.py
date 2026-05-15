"""
SQLAlchemy models for JobConnect application.
Import order is critical to avoid circular dependencies.
"""

# First, import the declarative base
from app.db.base_class import Base

# Import essential enums that don't depend on models
from app.models.user import UserRole
from app.models.job import JobStatus, JobLocationType
from app.models.payment import PaymentType, PaymentStatus
from app.models.job_application import ApplicationStatus
from app.models.escrow_transaction import EscrowStatus
from app.models.dispute import DisputeStatus
from app.models.enums import TaxPreference, WithdrawalRequestStatus, BookingStatus
from app.models.push_notification_log import PushDeliveryStatus
from app.models.scheduled_push_notification import ScheduledPushStatus

# Import core models in dependency order
from app.models.user import User  # Core model, others depend on this
from app.models.job import Job  # Depends on User

# Import models that only depend on User
from app.models.file import File
from app.models.user_session import UserSession
from app.models.badge import Badge
from app.models.user_badge import UserBadge, BadgeAwardStatus
from app.models.kyc import KYCSubmission
from app.models.message import Message
from app.models.notification import Notification
from app.models.push_notification_log import PushNotificationLog
from app.models.scheduled_push_notification import ScheduledPushNotification
from app.models.push_device import PushDevice
from app.models.expo_push_receipt import ExpoPushReceipt
from app.models.worker_profile import RecentWork, UserService
from app.models.otp import OTP
from app.models.category import Category
from app.models.newsletter import Newsletter
from app.models.tax_profile import WorkerTaxProfile, TaxProfileState
from app.models.bank_account import BankAccount

# Import models with payment dependencies
from app.models.payment import Payment  # Depends on User, Job
from app.models.job_application import JobApplication  # Depends on User, Job, Payment
from app.models.review import Review  # Depends on User, Job
from app.models.escrow_transaction import EscrowTransaction  # Depends on User, Job, Payment
from app.models.subscription import SubscriptionPlan
from app.models.dispute import Dispute
from app.models.dispute_message import DisputeMessage
from app.models.token_blacklist import TokenBlacklist
from app.models.recent_activity import RecentActivity
from app.models.service import Service
from app.models.booking import Booking  # Depends on User, Service, Payment
from app.models.referral import Referral, Reward, ReferralSettings
from app.models.transaction import Transaction
from app.models.waitlist import Waitlist
from app.models.withdrawal_request import WithdrawalRequest
from app.models.admin_audit_log import AdminAuditLog, AdminActionType


# Re-export all models and enums
__all__ = [
    # Base
    'Base',
    
    # Enums
    'UserRole',
    'JobStatus',
    'JobLocationType',
    'PaymentType',
    'PaymentStatus',
    'ApplicationStatus',
    'EscrowStatus',
    'DisputeStatus',
    'TaxProfileState',
    'TaxPreference',
    'WithdrawalRequestStatus',
    'BookingStatus',
    'PushDeliveryStatus',
    'ScheduledPushStatus',
    
    # Core models
    'User',
    'Job',
    
    # User-dependent models
    'File',
    'UserSession',
    'Badge',
    'UserBadge',
    'BadgeAwardStatus',
    'KYCSubmission',
    'Message',
    'Notification',
    'PushNotificationLog',
    'ScheduledPushNotification',
    'PushDevice',
    'ExpoPushReceipt',
    'RecentWork',
    'UserService',
    'OTP',
    'Category',
    'Newsletter',
    'WorkerTaxProfile',
    'BankAccount',
    
    # Complex dependency models
    'Payment',
    'JobApplication',
    'Review',
    'EscrowTransaction',
    'SubscriptionPlan',
    'Dispute',
    'DisputeMessage',
    'TokenBlacklist',
    'RecentActivity',
    'Service',
    'Booking',
    'Referral',
    'Reward',
    'ReferralSettings',
    'Transaction',
    'Waitlist',
    'WithdrawalRequest',
    'AdminAuditLog',
    'AdminActionType',
]

# Dictionary of all models for easy access
__models__ = {name: globals()[name] for name in __all__}
