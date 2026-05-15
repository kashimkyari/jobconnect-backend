from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
from sqlalchemy.orm import selectinload

from ..models.badge import Badge
from ..models.user import User
from ..models.user_badge import UserBadge, BadgeAwardStatus
from ..models.job import Job, JobStatus

logger = logging.getLogger(__name__)

class BadgeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_badges(self) -> List[Badge]:
        """Get all badges from the database."""
        query = select(Badge)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_user_badges(self, user_id: int) -> List[Badge]:
        """Get all badges a user has earned."""
        user = await self.db.get(User, user_id)
        if not user:
            logger.warning(f"User {user_id} not found when fetching badges")
            return []

        badges = await self.get_all_badges()
        earned_badges = []

        for badge in badges:
            if await self.check_badge_criteria(user, badge):
                earned_badges.append(badge)

        logger.info(f"User {user_id} has earned {len(earned_badges)} badges")
        return earned_badges

    async def check_badge_criteria(self, user: User, badge: Badge) -> bool:
        """Check if a user meets the criteria for a specific badge."""
        try:
            if badge.criteria_type == "rating":
                # For rating badges, use reputation_score (which is aliased to average_rating)
                meets_criteria = user.average_rating >= badge.criteria_value
                if meets_criteria:
                    logger.debug(f"User {user.id} meets rating criteria for badge '{badge.name}' (rating: {user.average_rating} >= {badge.criteria_value})")
                return meets_criteria
            elif badge.criteria_type == "jobs_completed":
                completed_jobs = await self.get_completed_jobs_count(user.id)
                meets_criteria = completed_jobs >= badge.criteria_value
                if meets_criteria:
                    logger.debug(f"User {user.id} meets jobs criteria for badge '{badge.name}' (completed: {completed_jobs} >= {badge.criteria_value})")
                return meets_criteria
            elif badge.criteria_type == "kyc_verified":
                # For KYC verified badge, check if user has completed KYC verification
                meets_criteria = user.is_kyc_verified
                if meets_criteria:
                    logger.debug(f"User {user.id} meets KYC criteria for badge '{badge.name}' (kyc_verified: {user.is_kyc_verified})")
                return meets_criteria
            else:
                logger.warning(f"Unknown badge criteria type: {badge.criteria_type}")
                return False
        except Exception as e:
            logger.error(f"Error checking badge criteria for user {user.id} and badge {badge.id}: {str(e)}")
            return False

    async def get_completed_jobs_count(self, user_id: int) -> int:
        """Get the number of completed jobs for a user."""
        try:
            query = select(Job).where(
                Job.worker_id == user_id,
                Job.status == JobStatus.COMPLETED
            )
            result = await self.db.execute(query)
            count = len(result.scalars().all())
            logger.debug(f"User {user_id} has {count} completed jobs")
            return count
        except Exception as e:
            logger.error(f"Error getting completed jobs count for user {user_id}: {str(e)}")
            return 0

    async def check_top_rated_badge_status(self, user_id: int) -> Dict[str, Any]:
        """
        Check if a user has or should have the 'Top Rated' badge.
        Returns comprehensive status information.
        """
        try:
            user = await self.db.get(User, user_id)
            if not user:
                return {
                    "has_badge": False,
                    "reputation_score": 0.0,
                    "required_score": 4.5,
                    "status": "user_not_found"
                }

            # Get Top Rated badge
            query = select(Badge).where(Badge.name == "Top Rated")
            result = await self.db.execute(query)
            top_rated_badge = result.scalars().first()

            if not top_rated_badge:
                logger.warning("Top Rated badge not found in database")
                return {
                    "has_badge": False,
                    "reputation_score": float(user.reputation_score or 0.0),
                    "required_score": 4.5,
                    "status": "badge_not_found"
                }

            has_badge = user.average_rating >= top_rated_badge.criteria_value
            reputation_score = float(user.reputation_score or 0.0)

            return {
                "has_badge": has_badge,
                "reputation_score": reputation_score,
                "required_score": top_rated_badge.criteria_value,
                "status": "qualified" if has_badge else "not_qualified",
                "score_difference": reputation_score - top_rated_badge.criteria_value
            }
        except Exception as e:
            logger.error(f"Error checking top rated badge status for user {user_id}: {str(e)}")
            return {
                "has_badge": False,
                "reputation_score": 0.0,
                "required_score": 4.5,
                "status": "error",
                "error": str(e)
            }

    async def get_badge_progress(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Get progress toward earning badges for a user.
        Useful for displaying badge progress in the UI.
        """
        try:
            user = await self.db.get(User, user_id)
            if not user:
                return []
            badges = await self.get_all_badges()
            progress_data = []

            for badge in badges:
                earned = await self.check_badge_criteria(user, badge)
                
                if badge.criteria_type == "rating":
                    current_value = float(user.reputation_score or 0.0)
                    progress_percent = min(100, int((current_value / badge.criteria_value) * 100))
                elif badge.criteria_type == "jobs_completed":
                    current_value = await self.get_completed_jobs_count(user.id)
                    progress_percent = min(100, int((current_value / badge.criteria_value) * 100))
                elif badge.criteria_type == "kyc_verified":
                    current_value = 1.0 if user.is_kyc_verified else 0.0
                    progress_percent = 100 if user.is_kyc_verified else 0
                else:
                    current_value = 0
                    progress_percent = 0

                progress_data.append({
                    "badge_id": badge.id,
                    "badge_name": badge.name,
                    "badge_description": badge.description,
                    "criteria_type": badge.criteria_type,
                    "earned": earned,
                    "current_value": current_value,
                    "required_value": badge.criteria_value,
                    "progress_percent": progress_percent
                })

            return progress_data
        except Exception as e:
            logger.error(f"Error getting badge progress for user {user_id}: {str(e)}")
            return []

    async def auto_award_badges(self, user_id: int) -> Dict[str, Any]:
        """
        Automatically award or revoke badges based on user's current criteria.
        Called whenever user's metrics change (job completed, review received, KYC verified, etc).
        Returns information about badges that were awarded or lost.
        """
        try:
            user = await self.db.get(User, user_id)
            if not user:
                logger.warning(f"User {user_id} not found when auto-awarding badges")
                return {"awarded": [], "revoked": [], "status": "user_not_found"}

            badges = await self.get_all_badges()
            awarded_badges = []
            revoked_badges = []

            for badge in badges:
                # Check if user meets criteria for this badge
                meets_criteria = await self.check_badge_criteria(user, badge)
                
                # Get existing badge record
                query = select(UserBadge).where(
                    and_(
                        UserBadge.user_id == user_id,
                        UserBadge.badge_id == badge.id,
                        UserBadge.status == BadgeAwardStatus.EARNED
                    )
                )
                result = await self.db.execute(query)
                existing_badge = result.scalars().first()

                if meets_criteria and not existing_badge:
                    # Award badge
                    new_badge = UserBadge(
                        user_id=user_id,
                        badge_id=badge.id,
                        status=BadgeAwardStatus.EARNED,
                        earned_at=datetime.utcnow()
                    )
                    self.db.add(new_badge)
                    awarded_badges.append({
                        "badge_id": badge.id,
                        "badge_name": badge.name,
                        "badge_description": badge.description
                    })
                    logger.info(f"Awarded badge '{badge.name}' to user {user_id}")

                elif not meets_criteria and existing_badge:
                    # Revoke badge
                    existing_badge.status = BadgeAwardStatus.LOST
                    existing_badge.lost_at = datetime.utcnow()
                    revoked_badges.append({
                        "badge_id": badge.id,
                        "badge_name": badge.name,
                        "badge_description": badge.description
                    })
                    logger.info(f"Revoked badge '{badge.name}' from user {user_id}")

            await self.db.commit()

            return {
                "awarded": awarded_badges,
                "revoked": revoked_badges,
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Error auto-awarding badges for user {user_id}: {str(e)}")
            return {
                "awarded": [],
                "revoked": [],
                "status": "error",
                "error": str(e)
            }
