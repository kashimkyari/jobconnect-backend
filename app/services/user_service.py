import os
import aiofiles
import json
from fastapi import UploadFile, HTTPException, status
from ..utils.json_encoder import DateTimeEncoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, func
from sqlalchemy.orm import selectinload
from typing import List
import uuid

from ..models.transaction import Transaction
from ..models.user import User, UserRole
from ..models.job import Job, JobStatus
from ..models.review import Review
from ..models.kyc import KYCSubmission
from ..models.job_application import JobApplication, ApplicationStatus
from ..models.user_badge import UserBadge, BadgeAwardStatus
from ..models.profile_view import ProfileView
from ..schemas.user import UserUpdate, UserInDB, UserProfile, JobPosterProfile
from ..config import settings
from ..utils.cache import get_cache, set_cache, delete_cache
from ..services.recent_activity_service import RecentActivityService
from ..schemas.recent_activity import RecentActivityCreate
from datetime import datetime
from typing import Optional

USER_CACHE_VERSION = "v1"

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user(self, user_id: int) -> User | None:
        user = await self.db.get(User, user_id)
        return user

    async def get_user_avatar_path(self, user_id: int) -> Optional[str]:
        user = await self.get_user(user_id)
        if user:
            return user.avatar_url
        return None

    async def get_user_profile(self, user_id: int) -> UserProfile | None:
        user = await self.db.get(User, user_id, options=[
            selectinload(User.services_offered),
            selectinload(User.recent_works),
            selectinload(User.jobs_posted)
        ])
        if not user:
            return None

        total_jobs_posted = len(user.jobs_posted)
        total_jobs_completed = sum(1 for job in user.jobs_posted if job.status == JobStatus.COMPLETED)

        profile_completion_percentage = self._calculate_profile_completion(user)

        return UserProfile(
            **user.__dict__,
            total_jobs_posted=total_jobs_posted,
            total_jobs_completed=total_jobs_completed,
            profile_completion_percentage=profile_completion_percentage,
        )

    def _calculate_profile_completion(self, user: User) -> int:
        total_fields = 10
        filled_fields = 0
        if user.first_name: filled_fields += 1
        if user.last_name: filled_fields += 1
        if user.email: filled_fields += 1
        if user.phone: filled_fields += 1
        if user.avatar_url: filled_fields += 1
        if user.about_me: filled_fields += 1
        if user.skills: filled_fields += 1
        if user.experience_level: filled_fields += 1
        if user.services_offered: filled_fields += 1
        if user.recent_works: filled_fields += 1
        return int((filled_fields / total_fields) * 100)

    @staticmethod
    def _employer_completion_fields(
        user: User,
        has_kyc_submission: bool,
        has_kyc_approved: bool,
    ) -> dict:
        """Profile strength fields used by employer home (server-side source of truth)."""
        return {
            "location": bool(user.location or user.city),
            "about_me": bool(user.about_me),
            "avatar_url": bool(user.avatar_url),
            "kyc_submitted": bool(has_kyc_submission),
            "kyc_approved": bool(has_kyc_approved),
        }

    @staticmethod
    def _calculate_profile_completion_from_fields(completion_fields: dict) -> int:
        completed = sum(1 for v in completion_fields.values() if v)
        return int((completed / len(completion_fields)) * 100) if completion_fields else 0

    @staticmethod
    def _get_completion_fields(completion_fields: dict) -> tuple:
        completed = [k for k, v in completion_fields.items() if v]
        remaining = [k for k, v in completion_fields.items() if not v]
        return completed, remaining

    async def _get_kyc_flags(self, user_id: int) -> tuple[bool, bool]:
        kyc_count_result = await self.db.execute(
            select(func.count(KYCSubmission.id)).where(KYCSubmission.user_id == user_id)
        )
        kyc_count = kyc_count_result.scalar() or 0
        has_kyc_submission = kyc_count > 0

        approved_kyc_result = await self.db.execute(
            select(func.count(KYCSubmission.id)).where(
                KYCSubmission.user_id == user_id,
                KYCSubmission.status == "approved",
            )
        )
        approved_kyc_count = approved_kyc_result.scalar() or 0
        has_kyc_approved = approved_kyc_count > 0
        return has_kyc_submission, has_kyc_approved

    async def get_employer_profile_completion_status(self, user_id: int):
        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        has_kyc_submission, has_kyc_approved = await self._get_kyc_flags(user_id)
        completion_fields = self._employer_completion_fields(
            user=user,
            has_kyc_submission=has_kyc_submission,
            has_kyc_approved=has_kyc_approved,
        )
        percentage = self._calculate_profile_completion_from_fields(completion_fields)
        completed, remaining = self._get_completion_fields(completion_fields)

        return {
            "completion_percentage": percentage,
            "fields_completed": completed,
            "fields_remaining": remaining,
        }

    @staticmethod
    def _format_time_ago(dt: Optional[datetime]) -> Optional[str]:
        if not dt:
            return None
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.utcnow()
        diff = now - dt
        seconds = max(int(diff.total_seconds()), 0)
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        if seconds < 604800:
            return f"{seconds // 86400}d ago"
        if seconds < 2592000:
            return f"{seconds // 604800}w ago"
        if seconds < 31536000:
            return f"{seconds // 2592000}mo ago"
        return f"{seconds // 31536000}y ago"

    async def get_job_poster_profile(self, user_id: int) -> JobPosterProfile | None:
        user = await self.db.get(User, user_id, options=[
            selectinload(User.jobs_posted),
            selectinload(User.reviews_received).selectinload(Review.reviewer),
            selectinload(User.reviews_received).selectinload(Review.reviewee),
            selectinload(User.reviews_received).selectinload(Review.job)
        ])
        if not user:
            return None

        total_jobs_posted = len(user.jobs_posted)
        total_jobs_completed = sum(1 for job in user.jobs_posted if job.status == JobStatus.COMPLETED)
        
        reviews_data = []
        sorted_received_reviews = sorted(
            user.reviews_received or [],
            key=lambda r: r.created_at or datetime.min,
            reverse=True
        )
        for review in sorted_received_reviews:
            reviewer_first = review.reviewer.first_name if review.reviewer else ""
            reviewer_last = review.reviewer.last_name if review.reviewer else ""
            reviewee_first = review.reviewee.first_name if review.reviewee else ""
            reviewee_last = review.reviewee.last_name if review.reviewee else ""
            reviewer_name = f"{reviewer_first} {reviewer_last}".strip() or "Anonymous"
            reviews_data.append({
                "id": review.id,
                "rating": review.rating,
                "comment": review.comment,
                "job_id": review.job_id,
                "reviewer_id": review.reviewer_id,
                "reviewee_id": review.reviewee_id,
                "created_at": review.created_at,
                "updated_at": review.updated_at,
                "reviewee_firstname": reviewee_first or None,
                "reviewee_lastname": reviewee_last or None,
                "reviewee_avatar": review.reviewee.avatar_url if review.reviewee else None,
                "reviewer_firstname": reviewer_first or None,
                "reviewer_lastname": reviewer_last or None,
                "reviewer_avatar": review.reviewer.avatar_url if review.reviewer else None,
                "reviewer_name": reviewer_name,
                "job_title": review.job.title if review.job else None,
                "time_ago": self._format_time_ago(review.created_at),
            })

        avg_rating = sum(review.rating for review in user.reviews_received) / len(user.reviews_received) if user.reviews_received else 0.0

        return JobPosterProfile(
            **user.__dict__,
            total_jobs_posted=total_jobs_posted,
            total_jobs_completed=total_jobs_completed,
            avg_rating=avg_rating,
            reviews=reviews_data
        )

    async def get_admin_user_id(self) -> Optional[int]:
        query = select(User.id).where(User.role == UserRole.ADMIN).limit(1)
        result = await self.db.execute(query)
        admin_user = result.scalar_one_or_none()
        return admin_user

    async def get_admin_user_ids(self) -> List[int]:
        query = select(User.id).where(User.role == UserRole.ADMIN)
        result = await self.db.execute(query)
        admin_users = result.scalars().all()
        return admin_users

    async def update_user(self, user_id: int, user_update: UserUpdate) -> User:
        user = await self.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        update_data = user_update.model_dump(exclude_unset=True)
        updated_fields = []
        for field, value in update_data.items():
            if getattr(user, field) != value:
                updated_fields.append(field)
            setattr(user, field, value)

        if updated_fields:
            activity_service = RecentActivityService(self.db)
            await activity_service.create_activity(
                RecentActivityCreate(
                    user_id=user_id,
                    activity_type="profile_update",
                    description=f"Profile updated: {', '.join(updated_fields)}",
                )
            )
            
        from sqlalchemy.exc import IntegrityError
        try:
            await self.db.commit()
            await self.db.refresh(user)
        except IntegrityError as e:
            await self.db.rollback()
            error_msg = str(e.orig).lower()
            if "phone" in error_msg:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number already exists")
            elif "email" in error_msg:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A unique constraint violation occurred")
        
        cache_key = f"user_{user_id}"
        await delete_cache(cache_key)
        
        return user

    async def update_user_profile(self, user_id: int, user_update: UserUpdate) -> User:
        user = await self.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        update_data = user_update.model_dump(exclude_unset=True)
        updated_fields = []
        for field, value in update_data.items():
            if getattr(user, field) != value:
                updated_fields.append(field)
            setattr(user, field, value)

        if updated_fields:
            activity_service = RecentActivityService(self.db)
            await activity_service.create_activity(
                RecentActivityCreate(
                    user_id=user_id,
                    activity_type="profile_update",
                    description=f"Profile updated: {', '.join(updated_fields)}",
                )
            )
            
        from sqlalchemy.exc import IntegrityError
        try:
            await self.db.commit()
            await self.db.refresh(user)
        except IntegrityError as e:
            await self.db.rollback()
            error_msg = str(e.orig).lower()
            if "phone" in error_msg:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number already exists")
            elif "email" in error_msg:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A unique constraint violation occurred")
        
        cache_key = f"user_{user_id}"
        await delete_cache(cache_key)
        
        return user


    async def upload_avatar(self, user_id: int, file: UploadFile) -> str:
        user = await self.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
            
        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/gif"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File type not allowed"
            )
            
        # Create upload directory if it doesn't exist
        upload_dir = os.path.join(settings.UPLOAD_DIR, "avatars")
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1]
        filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(upload_dir, filename)
        
        # Save file
        async with aiofiles.open(file_path, "wb") as buffer:
            content = await file.read()
            await buffer.write(content)
            
        # Update user avatar URL
        relative_path = f"/uploads/avatars/{filename}"
        user.avatar_url = relative_path
        await self.db.commit()
        
        return relative_path

    async def get_workers(self, skip: int = 0, limit: int = 10) -> List[User]:
        cache_key = f"workers_{USER_CACHE_VERSION}_{skip}_{limit}"
        cached_workers = await get_cache(cache_key)
        if cached_workers:
            return [UserInDB.model_validate(worker) for worker in json.loads(cached_workers)]

        query = (
            select(User)
            .where(User.role == UserRole.WORKER)
            .options(
                selectinload(User.services_offered),
                selectinload(User.recent_works)
            )
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        workers = result.scalars().unique().all()
        
        workers_schema = [UserInDB.from_orm(worker) for worker in workers]
        set_cache(cache_key, json.dumps([worker.model_dump() for worker in workers_schema], cls=DateTimeEncoder))
        return workers

    async def get_employers(self, current_user: User, skip: int = 0, limit: int = 10) -> List[User]:
        cache_key = f"employers_{USER_CACHE_VERSION}_{current_user.id if current_user.role == UserRole.WORKER else 'all'}_{skip}_{limit}"
        cached_employers = await get_cache(cache_key)
        if cached_employers:
            return [UserInDB.model_validate(employer) for employer in json.loads(cached_employers)]

        query = select(User).where(User.role == UserRole.EMPLOYER)

        if current_user.role == UserRole.WORKER:
            # Workers should only see employers they've worked with
            query = query.join(Job, Job.employer_id == User.id).join(
                JobApplication, JobApplication.job_id == Job.id
            ).where(
                JobApplication.worker_id == current_user.id,
                JobApplication.status == ApplicationStatus.ACCEPTED
            )

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        employers = result.scalars().unique().all()

        employers_schema = [UserInDB.from_orm(employer) for employer in employers]
        set_cache(cache_key, json.dumps([employer.model_dump() for employer in employers_schema], cls=DateTimeEncoder))
        return employers

    async def verify_user(self, user_id: int) -> User | None:
        user = await self.get_user(user_id)
        if not user:
            return None
            
        user.is_verified = True
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def deactivate_user(self, user_id: int) -> User | None:
        user = await self.get_user(user_id)
        if not user:
            return None
            
        user.is_active = False
        await self.db.commit()
        await self.db.refresh(user)
        
        cache_key = f"user_{user_id}"
        await delete_cache(cache_key)
        
        return user

    async def update_reputation(self, user_id: int, new_score: float) -> User | None:
        user = await self.get_user(user_id)
        if not user:
            return None
            
        user.reputation_score = new_score
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def search_users(self, query: str, skip: int = 0, limit: int = 10) -> List[User]:
        cache_key = f"search_users_{USER_CACHE_VERSION}_{query}_{skip}_{limit}"
        cached_users = await get_cache(cache_key)
        if cached_users:
            return [UserInDB.model_validate(user) for user in json.loads(cached_users)]

        search = f"%{query}%"
        db_query = (
            select(User)
            .where(
                or_(
                    User.first_name.ilike(search),
                    User.last_name.ilike(search),
                    User.email.ilike(search)
                )
            )
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(db_query)
        users = result.scalars().all()

        users_schema = [UserInDB.from_orm(user) for user in users]
        set_cache(cache_key, json.dumps([user.model_dump() for user in users_schema], cls=DateTimeEncoder))
        return users

    async def switch_user_role(self, user_id: int, new_role: UserRole) -> User:
        user = await self.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        user.role = new_role
        await self.db.commit()
        await self.db.refresh(user)

        # Invalidate user-related caches
        await delete_cache(f"user_{user_id}")
        await delete_cache(f"workers_{USER_CACHE_VERSION}_*")
        await delete_cache(f"employers_{USER_CACHE_VERSION}_*")

        return user

    async def get_wallet_details(self, user_id: int):
        """Get wallet balance, total in, and total out for a user."""
        user = await self.db.get(User, user_id)
        if not user:
            return None

        total_in_query = select(func.sum(Transaction.amount)).where(
            Transaction.user_id == user_id,
            Transaction.amount > 0
        )
        total_in_result = await self.db.execute(total_in_query)
        total_in = total_in_result.scalar_one_or_none() or 0

        total_out_query = select(func.sum(Transaction.amount)).where(
            Transaction.user_id == user_id,
            Transaction.amount < 0
        )
        total_out_result = await self.db.execute(total_out_query)
        total_out = total_out_result.scalar_one_or_none() or 0

        return {
            "balance": user.wallet_balance,
            "total_in": total_in,
            "total_out": abs(total_out)
        }

    async def get_user_stats(self, user_id: int):
        """Aggregates comprehensive user statistics for the auditing dashboard."""
        user = await self.db.get(User, user_id)
        if not user:
            return None

        # total_jobs_posted: jobs where user is employer
        jobs_posted_query = select(func.count(Job.id)).where(Job.employer_id == user_id)
        jobs_posted_result = await self.db.execute(jobs_posted_query)
        total_jobs_posted = jobs_posted_result.scalar() or 0

        # total_jobs_completed: jobs where user is employer or worker AND status is COMPLETED
        jobs_completed_query = select(func.count(Job.id)).where(
            or_(Job.employer_id == user_id, Job.worker_id == user_id),
            Job.status == JobStatus.COMPLETED
        )
        jobs_completed_result = await self.db.execute(jobs_completed_query)
        total_jobs_completed = jobs_completed_result.scalar() or 0

        # average_rating & total_reviews
        reviews_query = select(
            func.count(Review.id),
            func.avg(Review.rating)
        ).where(Review.reviewee_id == user_id)
        reviews_result = await self.db.execute(reviews_query)
        review_stats = reviews_result.fetchone()
        total_reviews = review_stats[0] or 0
        avg_rating = review_stats[1] or 0.0
        
        # profile_views
        views_query = select(func.count(ProfileView.id)).where(ProfileView.user_id == user_id)
        views_result = await self.db.execute(views_query)
        profile_views = views_result.scalar() or 0

        # badges_earned
        badges_query = select(func.count(UserBadge.id)).where(
            UserBadge.user_id == user_id,
            UserBadge.status == BadgeAwardStatus.EARNED
        )
        badges_result = await self.db.execute(badges_query)
        badges_earned = badges_result.scalar() or 0

        return {
            "total_jobs_posted": total_jobs_posted,
            "total_jobs_completed": total_jobs_completed,
            "average_rating": float(avg_rating),
            "total_reviews": total_reviews,
            "profile_views": profile_views,
            "member_since": user.created_at,
            "badges_earned": badges_earned
        }
