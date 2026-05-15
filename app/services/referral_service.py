from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import User
from app.models.referral import Referral, Reward
from app.services.notification_service import NotificationService
from app.models.notification import NotificationCategory
from app.schemas.notification import NotificationCreate
from sqlalchemy import select
import secrets

class ReferralService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_referral_code(self, user: User) -> str:
        """Generate and persist a unique referral code for a user."""
        if user.referral_code:
            return user.referral_code

        # Generate a reasonably short unique code
        for _ in range(5):
            code = f"JC{secrets.token_hex(3).upper()}"
            result = await self.db.execute(select(User).where(User.referral_code == code))
            if not result.scalar_one_or_none():
                user.referral_code = code
                self.db.add(user)
                await self.db.commit()
                await self.db.refresh(user)
                return code

        # Fallback to UUID hex if collisions keep happening (very unlikely)
        import uuid
        code = f"JC{uuid.uuid4().hex[:8].upper()}"
        user.referral_code = code
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return code

    async def get_referrals_by_user(self, user_id: int):
        """Return a list of referrals where the provided user is the referrer."""
        # Query referrals
        result = await self.db.execute(select(Referral).where(Referral.referrer_id == user_id).order_by(Referral.created_at.desc()))
        referrals = result.scalars().all()

        # Serialize minimal fields for the API
        out = []
        for r in referrals:
            out.append({
                "id": r.id,
                "referrer_id": r.referrer_id,
                "referred_id": r.referred_id,
                "status": r.status.value if r.status else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            })
        return out

    async def grant_signup_reward(self, referred_user: User):
        if not referred_user.referred_by:
            return

        referrer = await self.db.get(User, referred_user.referred_by)
        if not referrer:
            return

        # Grant 1 free job post and 1 free application
        referrer.remaining_job_posts += 1
        referrer.remaining_job_applications += 1

        # Create a reward record
        reward = Reward(
            user_id=referrer.id,
            reward_type="signup_bonus",
            amount=0  # No monetary value for this reward type
        )
        self.db.add(reward)
        await self.db.commit()

        # Notify the referrer
        notification_service = NotificationService(self.db)
        await notification_service.create_notification(
            NotificationCreate(
                user_id=referrer.id,
                title="Referral Reward!",
                message="You've earned 1 free job post and 1 free application for referring a new user!",
                category=NotificationCategory.REVIEWS_AND_REPUTATION
            )
        )

    async def grant_transaction_commission(self, user_id: int, transaction_amount: Decimal, transaction_id: int):
        user = await self.db.get(User, user_id)
        if not user or not user.referred_by:
            return

        referrer = await self.db.get(User, user.referred_by)
        if not referrer:
            return

        # Calculate commission (2.5%)
        commission = transaction_amount * Decimal('0.025')
        referrer.wallet_balance += commission

        # Create a reward record
        reward = Reward(
            user_id=referrer.id,
            transaction_id=transaction_id,
            reward_type="transaction_commission",
            amount=commission
        )
        self.db.add(reward)
        await self.db.commit()

        # Notify the referrer
        notification_service = NotificationService(self.db)
        await notification_service.create_notification(
            NotificationCreate(
                user_id=referrer.id,
                title="Referral Commission Earned!",
                message=f"You've earned a commission of ${commission:.2f} from a transaction made by your referral.",
                category=NotificationCategory.PAYMENTS_AND_WALLET
            )
        )
