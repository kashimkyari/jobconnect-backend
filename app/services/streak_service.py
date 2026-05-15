from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone, timedelta, time
from typing import Tuple, Optional
from ..models.user import User
from ..models.transaction import Transaction, TransactionType, TransactionStatus
from decimal import Decimal
import zoneinfo


class StreakService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.reset_inactivity_days = 3

    @staticmethod
    def get_user_day_start(client_timezone: str) -> datetime:
        """
        Get the start of the current day in the user's timezone.
        Returns a UTC datetime representing the start of today in their timezone.
        """
        try:
            tz = zoneinfo.ZoneInfo(client_timezone)
        except Exception:
            # Fall back to UTC if timezone is invalid
            tz = zoneinfo.ZoneInfo("UTC")
        
        # Get current time in user's timezone
        now_user_tz = datetime.now(tz)
        # Get midnight at start of today in user's timezone
        today_start_user_tz = now_user_tz.replace(hour=0, minute=0, second=0, microsecond=0)
        # Convert back to UTC
        today_start_utc = today_start_user_tz.astimezone(zoneinfo.ZoneInfo("UTC"))
        return today_start_utc

    @staticmethod
    def get_user_day_end(client_timezone: str) -> datetime:
        """
        Get the end of the current day in the user's timezone.
        Returns a UTC datetime representing the end of today in their timezone.
        """
        try:
            tz = zoneinfo.ZoneInfo(client_timezone)
        except Exception:
            tz = zoneinfo.ZoneInfo("UTC")
        
        now_user_tz = datetime.now(tz)
        today_end_user_tz = now_user_tz.replace(hour=23, minute=59, second=59, microsecond=999999)
        today_end_utc = today_end_user_tz.astimezone(zoneinfo.ZoneInfo("UTC"))
        return today_end_utc

    async def validate_claim_eligible(self, user: User, client_timezone: str = "UTC") -> Tuple[bool, Optional[str]]:
        """
        Validate if user is eligible to claim daily streak today.
        
        Returns:
            Tuple[bool, Optional[str]]: (is_eligible, error_message)
            - (True, None) if eligible
            - (False, error_message) if not eligible
        """
        if not user.is_active:
            return False, "User account is not active"
        
        # Check if user has already claimed today
        if user.last_streak_claim_at:
            day_start = self.get_user_day_start(client_timezone)
            # If last claim was after the start of today in user's timezone, they already claimed
            if user.last_streak_claim_at >= day_start:
                return False, "Already claimed today"
        
        return True, None

    @staticmethod
    def calculate_credit_reward(streak_day: int) -> Decimal:
        """
        Calculate exponential credit reward based on streak day.
        
        Formula:
        - Day 1: ₦1
        - Day 2: ₦1
        - Day 3: ₦5
        - Day 7: ₦20
        - Day 14: ₦50
        - Day 30: ₦100
        - Day 60: ₦150
        - Day 90+: ₦200
        
        Linear scaling between milestones.
        """
        milestones = {
            1: Decimal("1"),
            3: Decimal("5"),
            7: Decimal("20"),
            14: Decimal("50"),
            30: Decimal("100"),
            60: Decimal("150"),
            90: Decimal("200"),
        }
        
        # Find the appropriate milestone
        if streak_day >= 90:
            return milestones[90]
        
        # Find milestone boundaries
        sorted_milestones = sorted(milestones.items())
        
        for i, (day, amount) in enumerate(sorted_milestones):
            if streak_day == day:
                return amount
            elif streak_day < day:
                if i == 0:
                    return milestones[1]
                
                # Linear interpolation between milestones
                prev_day, prev_amount = sorted_milestones[i - 1]
                next_day, next_amount = sorted_milestones[i]
                
                # Scale proportionally between previous and next milestone
                progress = (streak_day - prev_day) / (next_day - prev_day)
                reward = prev_amount + (next_amount - prev_amount) * Decimal(str(progress))
                return reward.quantize(Decimal("0.01"))
        
        return milestones[1]  # Default to day 1 reward

    async def process_daily_claim(
        self,
        user: User,
        client_timezone: str = "UTC"
    ) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Process a daily streak claim for a user.
        
        Atomically:
        1. Validate eligibility
        2. Increment streak
        3. Calculate reward
        4. Award credits to wallet
        5. Update last_streak_claim_at timestamp
        
        Returns:
            Tuple[bool, Optional[str], Optional[dict]]:
            - (True, None, {data}) on success
            - (False, error_message, None) on failure
            
            Success data contains:
            {
                "streak_count": int,
                "credits_awarded": Decimal,
                "total_credits": Decimal,
                "is_milestone": bool,
                "next_milestone_day": int
            }
        """
        # Validate eligibility
        is_eligible, error_msg = await self.validate_claim_eligible(user, client_timezone)
        if not is_eligible:
            return False, error_msg, None
        
        try:
            # Check if streak should reset
            # Streak resets if last claim was more than reset_inactivity_days ago
            if user.last_streak_claim_at:
                day_start = self.get_user_day_start(client_timezone)
                inactivity_cutoff = day_start - timedelta(days=self.reset_inactivity_days)
                
                # If last claim was before the cutoff, reset streak to 0
                if user.last_streak_claim_at < inactivity_cutoff:
                    user.streak_count = 0
            
            # Increment streak
            user.streak_count = (user.streak_count or 0) + 1
            new_streak_count = user.streak_count
            
            # Calculate credit reward
            credits_awarded = self.calculate_credit_reward(new_streak_count)
            
            # Update wallet balance
            old_balance = user.wallet_balance or Decimal("0")
            user.wallet_balance = old_balance + credits_awarded
            new_balance = user.wallet_balance
            
            # Update timestamp
            now_utc = datetime.now(timezone.utc)
            user.last_streak_claim_at = now_utc
            
            # Create transaction record for auditing
            transaction = Transaction(
                user_id=user.id,
                transaction_type=TransactionType.STREAK,
                amount=credits_awarded,
                description=f"Daily streak reward (Day {new_streak_count})",
                status=TransactionStatus.SUCCESS
            )
            self.db.add(transaction)
            
            # Commit changes
            self.db.add(user)
            await self.db.flush()  # Flush to get any database-generated values
            await self.db.commit()
            
            # Determine if this is a milestone day
            milestone_days = [3, 7, 14, 30, 60, 90]
            is_milestone = new_streak_count in milestone_days
            
            # Calculate next milestone
            next_milestone_day = next((d for d in milestone_days if d > new_streak_count), None)
            
            return True, None, {
                "streak_count": new_streak_count,
                "credits_awarded": float(credits_awarded),
                "total_credits": float(new_balance),
                "is_milestone": is_milestone,
                "next_milestone_day": next_milestone_day or (90 + 30),  # After 90, every 30 days
            }
            
        except Exception as e:
            await self.db.rollback()
            return False, f"Failed to process claim: {str(e)}", None

    async def get_streak_history(
        self,
        user: User,
        days_back: int = 120,
        client_timezone: str = "UTC",
    ) -> dict:
        """
        Build server-authoritative streak history by day for the requested window.
        """
        safe_days_back = max(1, min(int(days_back or 120), 365))
        try:
            tz = zoneinfo.ZoneInfo(client_timezone or "UTC")
        except Exception:
            tz = zoneinfo.ZoneInfo("UTC")

        now_local = datetime.now(tz)
        end_local_date = now_local.date()

        first_claim_query = (
            select(func.min(Transaction.created_at))
            .where(
                Transaction.user_id == user.id,
                Transaction.transaction_type == TransactionType.STREAK,
                Transaction.status == TransactionStatus.SUCCESS,
            )
        )
        first_claim_result = await self.db.execute(first_claim_query)
        first_claim_at = first_claim_result.scalar_one_or_none()
        if first_claim_at and first_claim_at.tzinfo is None:
            first_claim_at = first_claim_at.replace(tzinfo=timezone.utc)

        max_window_start = end_local_date - timedelta(days=safe_days_back - 1)
        if first_claim_at:
            first_claim_local_date = first_claim_at.astimezone(tz).date()
            start_local_date = max(first_claim_local_date, max_window_start)
        else:
            # No streak history yet: keep a short relevant window.
            start_local_date = end_local_date - timedelta(days=min(29, safe_days_back - 1))

        start_local_dt = datetime.combine(start_local_date, time.min, tzinfo=tz)
        end_local_dt = datetime.combine(end_local_date + timedelta(days=1), time.min, tzinfo=tz)
        start_utc = start_local_dt.astimezone(zoneinfo.ZoneInfo("UTC"))
        end_utc = end_local_dt.astimezone(zoneinfo.ZoneInfo("UTC"))

        streak_tx_query = (
            select(Transaction.created_at)
            .where(
                Transaction.user_id == user.id,
                Transaction.transaction_type == TransactionType.STREAK,
                Transaction.status == TransactionStatus.SUCCESS,
                Transaction.created_at >= start_utc,
                Transaction.created_at < end_utc,
            )
            .order_by(Transaction.created_at.asc())
        )
        streak_tx_result = await self.db.execute(streak_tx_query)
        created_rows = streak_tx_result.scalars().all()

        claimed_dates = set()
        for created_at in created_rows:
            if not created_at:
                continue
            created_dt = created_at
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            local_date = created_dt.astimezone(tz).date()
            claimed_dates.add(local_date.isoformat())

        days = []
        best_streak = 0
        running = 0
        cursor = start_local_date
        while cursor <= end_local_date:
            iso = cursor.isoformat()
            claimed = iso in claimed_dates
            days.append({
                "date": cursor,
                "claimed": claimed,
            })
            if claimed:
                running += 1
                if running > best_streak:
                    best_streak = running
            else:
                running = 0
            cursor += timedelta(days=1)

        return {
            "streak_count": int(user.streak_count or 0),
            "last_streak_claim_at": user.last_streak_claim_at,
            "first_streak_claim_at": first_claim_at,
            "total_claimed_days": len(claimed_dates),
            "best_streak": best_streak,
            "days_back": safe_days_back,
            "calendar_start_date": start_local_date,
            "calendar_end_date": end_local_date,
            "has_history": len(claimed_dates) > 0,
            "days": days,
        }
