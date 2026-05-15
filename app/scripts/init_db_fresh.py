import sys
import os
import logging
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import sqlalchemy as sa
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path to allow imports from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Get database URL from environment or fallback to settings
from app.config import settings
DATABASE_URL = os.getenv('DATABASE_URL', settings.DATABASE_URL)

# Import all models to ensure they are registered with the Base metadata
from app.models.admin_audit_log import AdminAuditLog
from app.models.badge import Badge
from app.models.bank_account import BankAccount
from app.models.blocked_worker import BlockedWorker
from app.models.category import Category
from app.models.dispute import Dispute
from app.models.escrow_transaction import EscrowTransaction
from app.models.file import File
from app.models.job import Job
from app.models.job_application import JobApplication
from app.models.kyc import KYCSubmission
from app.models.message import Message
from app.models.newsletter import Newsletter
from app.models.notification import Notification
from app.models.notification_settings import NotificationSettings
from app.models.otp import OTP
from app.models.payment import Payment
from app.models.profile_view import ProfileView
from app.models.push_notification_log import PushNotificationLog
from app.models.push_device import PushDevice
from app.models.expo_push_receipt import ExpoPushReceipt
from app.models.recent_activity import RecentActivity
from app.models.referral import Referral
from app.models.review import Review
from app.models.service import Service
from app.models.subscription import SubscriptionPlan
from app.models.story import Story, StoryView
from app.models.token_blacklist import TokenBlacklist
from app.models.transaction import Transaction
from app.models.user import User
from app.models.user_badge import UserBadge
from app.models.enums import UserRole
from app.models.waitlist import Waitlist
from app.models.withdrawal_request import WithdrawalRequest
from app.models.worker_profile import RecentWork, UserService
from app.db.base_class import Base
from app.utils.security import get_password_hash

async def init_db_fresh():
    """
    Initializes the database by dropping and recreating all tables,
    and creates a default admin user.
    """
    logger.info("Starting fresh database initialization...")
    logger.info(f"Using database URL: {DATABASE_URL}")
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async def wait_for_db(retries=20, delay=1.0):
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                async with engine.connect() as conn:
                    await conn.execute(sa.text('SELECT 1'))
                logger.info("Database is available")
                return True
            except Exception as e:
                last_exc = e
                logger.info(f"Database not ready (attempt {attempt}/{retries}), retrying in {delay}s...")
                await asyncio.sleep(delay)
        logger.error(f"Database did not become available in time: {last_exc}")
        return False
    
    try:
        if not await wait_for_db():
            raise Exception("Database connection failed")

        async with engine.begin() as conn:
            logger.info("Dropping existing enum types to ensure a clean state...")
            enum_types = [
                "paymenttype", "paymentstatus", "transactionstatus", 
                "transactiontype", "userrole", "jobstatus", "applicationstatus",
                "disputestatus", "disputereason", "notificationcategory", "pricingmodel"
            ]
            for enum_type in enum_types:
                try:
                    await conn.execute(sa.text(f"DROP TYPE IF EXISTS {enum_type} CASCADE;"))
                    logger.info(f"Dropped enum type {enum_type}")
                except Exception as e:
                    logger.warning(f"Could not drop enum type {enum_type}: {e}")

            logger.info("Dropping existing public schema to ensure a clean state...")
            await conn.execute(sa.text('DROP SCHEMA public CASCADE;'))
            logger.info("Recreating public schema...")
            await conn.execute(sa.text('CREATE SCHEMA public;'))
            
            logger.info("Creating all tables based on the current models...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("All tables created successfully.")

        # Create default admin user
        async with async_session() as session:
            async with session.begin():
                logger.info("Creating default admin user...")
                admin_email = settings.DEFAULT_ADMIN_EMAIL
                admin_password = settings.DEFAULT_ADMIN_PASSWORD
                
                # Check if admin user already exists
                result = await session.execute(
                    sa.select(User).where(User.email == admin_email)
                )
                if result.scalar_one_or_none() is None:
                    hashed_password = get_password_hash(admin_password)
                    new_admin = User(
                        email=admin_email,
                        hashed_password=hashed_password,
                        role=UserRole.ADMIN,
                        is_active=True,
                        is_verified=True,
                        first_name="Admin",
                        last_name="User"
                    )
                    session.add(new_admin)
                    logger.info(f"Admin user '{admin_email}' created successfully.")
                else:
                    logger.info(f"Admin user '{admin_email}' already exists.")

                # Create default categories
                logger.info("Creating default categories...")
                default_categories = [
                    "Healthcare",
                    "Cleaning", 
                    "Tutoring & Education",
                    "Logistics & Delivery",
                    "Web Development",
                    "Graphic Design",
                    "Writing & Content",
                    "Photography",
                    "Plumbing & Handyman",
                    "Consulting",
                    "Marketing & Advertising",
                    "Video Production",
                    "Pet Care",
                    "Fitness & Training",
                    "Event Planning",
                ]
                
                for category_name in default_categories:
                    result = await session.execute(
                        sa.select(Category).where(Category.name == category_name)
                    )
                    if result.scalar_one_or_none() is None:
                        session.add(Category(name=category_name))
                        logger.info(f"Created category '{category_name}'")
                
                logger.info(f"Default categories created successfully ({len(default_categories)} total).")

                # Create default subscription plans
                logger.info("Creating default subscription plans...")
                default_plans = [
                    # Worker Plans
                    {
                        "name": "Freelancer Basic",
                        "label": "Freelancer Basic",
                        "user_type": "worker",
                        "description": "Reduced commission (1.0% vs 1.5%)",
                        "price_monthly": 2999.0,
                        "price_annually": 29990.0,
                        "currency": "NGN",
                        "features": {
                            "commission_rate": 1.0,
                            "tax_documents": True,
                            "unlimited_applications": True,
                            "support_level": "standard"
                        },
                        "is_active": True,
                        "is_recommended": False,
                        "sort_order": 1,
                    },
                    {
                        "name": "Freelancer Pro",
                        "label": "Freelancer Pro",
                        "user_type": "worker",
                        "description": "Lower commission (0.7% vs 1.5%) with advanced features",
                        "price_monthly": 9999.0,
                        "price_annually": 99990.0,
                        "currency": "NGN",
                        "features": {
                            "commission_rate": 0.7,
                            "featured_profile": True,
                            "unlimited_applications": True,
                            "advanced_analytics": True,
                            "support_level": "priority",
                            "featured_boosts_per_month": 2,
                            "tax_compliance": True
                        },
                        "is_active": True,
                        "is_recommended": True,
                        "sort_order": 2,
                    },
                    {
                        "name": "Freelancer Enterprise",
                        "label": "Freelancer Enterprise",
                        "user_type": "worker",
                        "description": "Minimal commission (0.5% vs 1.5%) with premium features",
                        "price_monthly": 29999.0,
                        "price_annually": 299990.0,
                        "currency": "NGN",
                        "features": {
                            "commission_rate": 0.5,
                            "premium_featured_profile": True,
                            "unlimited_applications": True,
                            "advanced_analytics": True,
                            "api_access": True,
                            "featured_boosts_per_month": 5,
                            "dedicated_account_manager": True,
                            "custom_branding": True
                        },
                        "is_active": True,
                        "is_recommended": False,
                        "sort_order": 3,
                    },
                    # Employer Plans
                    {
                        "name": "Employer Starter",
                        "label": "Employer Starter",
                        "user_type": "employer",
                        "description": "Post up to 10 jobs per month with basic support",
                        "price_monthly": 4999.0,
                        "price_annually": 49990.0,
                        "currency": "NGN",
                        "features": {
                            "jobs_per_month": 10,
                            "support_level": "standard",
                            "candidate_analytics": True,
                            "team_members": 1,
                            "job_templates": True
                        },
                        "is_active": True,
                        "is_recommended": False,
                        "sort_order": 4,
                    },
                    {
                        "name": "Employer Professional",
                        "label": "Employer Professional",
                        "user_type": "employer",
                        "description": "Post up to 50 jobs per month with advanced recruiter tools",
                        "price_monthly": 14999.0,
                        "price_annually": 149990.0,
                        "currency": "NGN",
                        "features": {
                            "jobs_per_month": 50,
                            "featured_job_slots": 2,
                            "advanced_recruiter_tools": True,
                            "candidate_analytics": True,
                            "support_level": "priority",
                            "team_members": 3,
                            "ai_recommendations": True,
                            "candidate_screening": True
                        },
                        "is_active": True,
                        "is_recommended": True,
                        "sort_order": 5,
                    },
                    {
                        "name": "Employer Enterprise",
                        "label": "Employer Enterprise",
                        "user_type": "employer",
                        "description": "Unlimited job postings with full recruiter toolkit and API access",
                        "price_monthly": 39999.0,
                        "price_annually": 399990.0,
                        "currency": "NGN",
                        "features": {
                            "jobs_unlimited": True,
                            "featured_job_slots": 10,
                            "full_recruiter_toolkit": True,
                            "advanced_analytics": True,
                            "api_access": True,
                            "team_members": None,  # unlimited
                            "dedicated_account_manager": True,
                            "custom_branding": True,
                            "white_label": True
                        },
                        "is_active": True,
                        "is_recommended": False,
                        "sort_order": 6,
                    },
                ]

                for plan_data in default_plans:
                    result = await session.execute(
                        sa.select(SubscriptionPlan).where(SubscriptionPlan.name == plan_data["name"])
                    )
                    if result.scalar_one_or_none() is None:
                        session.add(SubscriptionPlan(**plan_data))
                
                logger.info("Default subscription plans created successfully.")

                # Create default badges
                logger.info("Creating default badges...")
                default_badges = [
                    {
                        "name": "KYC Verified",
                        "description": "Complete identity verification (KYC).",
                        "icon_url": "https://example.com/kyc_verified.png",
                        "criteria_type": "kyc_verified",
                        "criteria_value": 1.0,
                    },
                    {
                        "name": "Top Rated",
                        "description": "Maintain a rating of 4.5 or higher.",
                        "icon_url": "https://example.com/top_rated.png",
                        "criteria_type": "rating",
                        "criteria_value": 4.5,
                    },
                    {
                        "name": "First Job",
                        "description": "Complete your first job.",
                        "icon_url": "https://example.com/first_job.png",
                        "criteria_type": "jobs_completed",
                        "criteria_value": 1,
                    },
                    {
                        "name": "Productive",
                        "description": "Complete 5 jobs.",
                        "icon_url": "https://example.com/productive.png",
                        "criteria_type": "jobs_completed",
                        "criteria_value": 5,
                    },
                    {
                        "name": "Reliable",
                        "description": "Complete 10 jobs.",
                        "icon_url": "https://example.com/reliable.png",
                        "criteria_type": "jobs_completed",
                        "criteria_value": 10,
                    },
                    {
                        "name": "Prolific",
                        "description": "Complete 50 jobs.",
                        "icon_url": "https://example.com/prolific.png",
                        "criteria_type": "jobs_completed",
                        "criteria_value": 50,
                    },
                    {
                        "name": "Century",
                        "description": "Complete 100 jobs.",
                        "icon_url": "https://example.com/century.png",
                        "criteria_type": "jobs_completed",
                        "criteria_value": 100,
                    },
                ]

                for badge_data in default_badges:
                    result = await session.execute(
                        sa.select(Badge).where(Badge.name == badge_data["name"])
                    )
                    if result.scalar_one_or_none() is None:
                        session.add(Badge(**badge_data))
                
                logger.info("Default badges created successfully.")

            
    except Exception as e:
        logger.error(f"Error during fresh database initialization: {e}")
        logger.error("Stack trace:", exc_info=True)
        raise
    
    finally:
        logger.info("Closing database connection...")
        await engine.dispose()
        logger.info("Fresh database initialization process finished.")

if __name__ == "__main__":
    asyncio.run(init_db_fresh())
