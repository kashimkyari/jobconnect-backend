# Import all the models, so that Base has them before being
# imported by Alembic
from app.db.base_class import Base
from app.models.boost_transaction import BoostTransaction
from app.models.bank_account import BankAccount
from app.models.user import User
from app.models.job import Job
from app.models.job_application import JobApplication
from app.models.review import Review
from app.models.notification import Notification
from app.models.transaction import Transaction
from app.models.payment import Payment
from app.models.kyc import KYCSubmission
from app.models.message import Message
from app.models.escrow_transaction import EscrowTransaction
from app.models.dispute import Dispute
from app.models.subscription import SubscriptionPlan
from app.models.file import File
from app.models.otp import OTP
from app.models.token_blacklist import TokenBlacklist
from app.models.worker_profile import RecentWork, UserService
from app.models.category import Category
from app.models.badge import Badge
from app.models.user_badge import UserBadge
from app.models.dispute_message import DisputeMessage
from app.models.dispute_attachment import DisputeAttachment
from app.models.referral import Referral, Reward
from app.models.waitlist import Waitlist
from app.models.story import Story, StoryView
from app.models.newsletter import NewsletterSubscriber
from app.models.recent_activity import RecentActivity
from app.models.profile_view import ProfileView
from app.models.notification_settings import NotificationSettings
from app.models.blocked_worker import BlockedWorker
from app.models.push_device import PushDevice
from app.models.expo_push_receipt import ExpoPushReceipt
