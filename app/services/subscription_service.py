from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, status
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import uuid

from app.models.subscription import SubscriptionPlan
from app.models.user import User
from app.schemas.subscription import SubscriptionPlanCreate
from app.services.notification_service import NotificationService
from app.models.notification import NotificationCategory
from app.schemas.notification import NotificationCreate
from app.services.transaction_service import TransactionService
from app.models.transaction import TransactionType

class SubscriptionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_subscription_plan(self, plan: SubscriptionPlanCreate):
        db_plan = SubscriptionPlan(**plan.dict())
        self.db.add(db_plan)
        await self.db.commit()
        await self.db.refresh(db_plan)
        return db_plan

    async def get_subscription_plans(self):
        result = await self.db.execute(select(SubscriptionPlan))
        return result.scalars().all()

    async def subscribe_user(self, user_id: int, plan_id: int, billing_cycle: str):
        user = await self.db.get(User, user_id)
        plan = await self.db.get(SubscriptionPlan, plan_id)

        if not user or not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User or plan not found")

        price = Decimal(plan.price_monthly) if billing_cycle == 'monthly' else Decimal(plan.price_annually)

        if user.wallet_balance < price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient wallet balance. Please fund your wallet.",
            )

        # Create unique transaction reference with UUID to avoid duplicates
        transaction_service = TransactionService(self.db)
        unique_ref = f"sub_{user.id}_{plan.id}_{uuid.uuid4().hex[:8]}"
        
        await transaction_service.create_transaction(
            user_id=user.id,
            amount=-price,
            transaction_type=TransactionType.SUBSCRIPTION_PAYMENT.value,
            reference=unique_ref,
            description=f"Subscription to {plan.name} ({billing_cycle})",
        )

        # Calculate subscription expiry based on billing cycle
        now = datetime.now(timezone.utc)
        if billing_cycle == 'monthly':
            expiry_date = now + timedelta(days=30)
        elif billing_cycle == 'annual':
            expiry_date = now + timedelta(days=365)
        else:
            expiry_date = now + timedelta(days=30)  # Default to 30 days

        # Update user's subscription
        user.subscription_plan_id = plan.id
        user.subscription_status = True
        user.subscription_expiry = expiry_date
        
        # Reset usage limits based on the new plan
        features = plan.features or {}
        user.remaining_job_posts = features.get("job_posts", 0)
        user.remaining_job_applications = features.get("job_applications", 0)

        await self.db.commit()
        await self.db.refresh(user)

        # Create a notification for the user
        notification_service = NotificationService(self.db)
        await notification_service.create_notification(
            NotificationCreate(
                user_id=user.id,
                title="Subscription Activated",
                message=f"You have successfully subscribed to the {plan.name} plan.",
                category=NotificationCategory.PAYMENTS_AND_WALLET
            )
        )

        return plan

    async def check_user_limits(self, user_id: int, action: str) -> bool:
        user = await self.db.get(User, user_id)
        if not user:
            return False

        if not user.subscription_plan_id:
            return False

        plan = await self.db.get(SubscriptionPlan, user.subscription_plan_id)
        if not plan:
            return False

        features = plan.features or {}
        if action == "post_job":
            limit = features.get("job_posts", 0)
            return user.remaining_job_posts > 0 if limit > 0 else True
        elif action == "apply_job":
            limit = features.get("job_applications", 0)
            return user.remaining_job_applications > 0 if limit > 0 else True
        
        return False

    async def decrement_limit(self, user_id: int, action: str):
        user = await self.db.get(User, user_id)
        if not user:
            return

        if action == "post_job":
            if user.remaining_job_posts > 0:
                user.remaining_job_posts -= 1
        elif action == "apply_job":
            if user.remaining_job_applications > 0:
                user.remaining_job_applications -= 1
        
        await self.db.commit()

    async def get_user_subscription(self, user_id: int):
        user = await self.db.get(User, user_id)
        if not user or not user.subscription_status or not user.subscription_plan_id:
            return None
        
        plan = await self.db.get(SubscriptionPlan, user.subscription_plan_id)
        if not plan:
            return None
        
        # Calculate refund window (3 days)
        now = datetime.now(timezone.utc)
        days_remaining = 0
        is_refundable = False
        
        if user.subscription_expiry:
            days_remaining = (user.subscription_expiry - now).days
            # Check if within 3 days of subscription start (approximately)
            # subscription_expiry is current_time + 30 days when subscribed
            # So if remaining days > 27, it means < 3 days have passed
            is_refundable = days_remaining > 27
        
        return {
            "plan": plan,
            "subscription_status": user.subscription_status,
            "subscription_expiry": user.subscription_expiry,
            "days_remaining": max(0, days_remaining),
            "is_refundable": is_refundable
        }

    async def cancel_subscription(self, user_id: int) -> dict:
        """
        Cancel user subscription and process refund if within 3 days.
        """
        user = await self.db.get(User, user_id)
        if not user or not user.subscription_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active subscription found."
            )

        plan = await self.db.get(SubscriptionPlan, user.subscription_plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription plan not found."
            )

        # Check if within 3-day refund window
        now = datetime.now(timezone.utc)
        days_remaining = (user.subscription_expiry - now).days if user.subscription_expiry else 0
        
        # Calculate days since subscription started (assuming 30-day monthly cycle as default)
        # For a more accurate calculation, we assume monthly subscriptions (30 days)
        assumed_subscription_days = 30
        days_since_subscription = max(0, assumed_subscription_days - days_remaining)
        
        # If more than 27 days remaining, it means less than 3 days have passed
        # and user is eligible for refund
        refund_amount = Decimal(0)
        refund_message = "Subscription canceled. No refund provided."
        
        if days_remaining > 27:
            # Full refund within 3 days
            # Determine which price to refund based on billing cycle
            # We'll refund the monthly price (safer assumption)
            price = Decimal(plan.price_monthly)
            refund_amount = price
            refund_message = f"Subscription canceled. Refund of ₦{refund_amount} processed."
            
            # Process refund transaction
            transaction_service = TransactionService(self.db)
            await transaction_service.create_transaction(
                user_id=user.id,
                amount=refund_amount,
                transaction_type=TransactionType.REFUND.value,
                reference=f"refund_sub_{user.id}_{uuid.uuid4().hex[:8]}",
                description=f"Subscription refund for {plan.name}",
            )
            
            # Add refund to wallet
            user.wallet_balance = Decimal(user.wallet_balance) + refund_amount

        # Deactivate subscription
        user.subscription_status = False
        user.subscription_plan_id = None
        user.subscription_expiry = None
        
        # Reset usage limits
        user.remaining_job_posts = 0
        user.remaining_job_applications = 0

        await self.db.commit()
        await self.db.refresh(user)

        # Send notification
        notification_service = NotificationService(self.db)
        await notification_service.create_notification(
            NotificationCreate(
                user_id=user.id,
                title="Subscription Canceled",
                message=refund_message,
                category=NotificationCategory.PAYMENTS_AND_WALLET
            )
        )

        return {
            "success": True,
            "message": refund_message,
            "refund_amount": float(refund_amount),
            "days_since_subscription": days_since_subscription
        }

    async def is_user_subscribed(self, user_id: int) -> bool:
        user = await self.db.get(User, user_id)
        if not user:
            return False
        return user.subscription_status
