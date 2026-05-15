from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from app.models.user import User, UserRole
from app.schemas.user import WorkerProfileUpdate
from app.models.worker_profile import UserService, RecentWork
from app.models.kyc import KYCSubmission
from app.models.service import Service
from app.models.review import Review
from app.services.notification_service import NotificationService

class WorkerService:
    @staticmethod
    def _completion_fields(
        user: User,
        has_created_service: bool,
        has_kyc_submission: bool,
        has_kyc_approved: bool,
    ) -> dict:
        """Profile strength fields used by worker home (server-side source of truth)."""
        return {
            'location': bool(user.location),
            'about_me': bool(user.about_me),
            'service_category': bool(user.service_category),
            'avatar_url': bool(user.avatar_url),
            'skills': bool(user.skills and len(user.skills) > 0),
            'created_service': bool(has_created_service),
            'kyc_submitted': bool(has_kyc_submission),
            'kyc_approved': bool(has_kyc_approved),
        }

    @staticmethod
    def _calculate_profile_completion(completion_fields: dict) -> int:
        """Calculate profile completion percentage from completion fields."""
        completed = sum(1 for v in completion_fields.values() if v)
        return int((completed / len(completion_fields)) * 100)

    @staticmethod
    def _get_completion_fields(completion_fields: dict) -> tuple:
        """Get lists of completed and remaining field keys."""
        completed = [k for k, v in completion_fields.items() if v]
        remaining = [k for k, v in completion_fields.items() if not v]
        return completed, remaining

    @staticmethod
    async def _get_profile_strength_inputs(db: AsyncSession, user_id: int) -> tuple[bool, bool, bool]:
        """Resolve server-side inputs for profile strength calculation."""
        services_count_result = await db.execute(
            select(func.count(Service.id)).where(Service.worker_id == user_id)
        )
        services_count = services_count_result.scalar() or 0
        has_created_service = services_count > 0

        kyc_count_result = await db.execute(
            select(func.count(KYCSubmission.id)).where(KYCSubmission.user_id == user_id)
        )
        kyc_count = kyc_count_result.scalar() or 0
        has_kyc_submission = kyc_count > 0

        approved_kyc_result = await db.execute(
            select(func.count(KYCSubmission.id)).where(
                KYCSubmission.user_id == user_id,
                KYCSubmission.status == "approved",
            )
        )
        approved_kyc_count = approved_kyc_result.scalar() or 0
        has_kyc_approved = approved_kyc_count > 0
        return has_created_service, has_kyc_submission, has_kyc_approved

    @staticmethod
    async def get_user_profile(db: AsyncSession, user_id: int):
        query = (
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.recent_works),
                selectinload(User.services_offered),
                selectinload(User.subscription_plan),
                selectinload(User.payments),
                selectinload(User.jobs_posted)
            )
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        # Manually set the additional fields required by the UserProfile schema
        user.total_jobs_posted = len(user.jobs_posted)
        user.total_jobs_completed = len([job for job in user.jobs_posted if job.status == "completed"])
        user.subscription = user.subscription_plan
        user.recent_transactions = user.payments[:5] if user.payments else []

        review_stats = await db.execute(
            select(
                func.avg(Review.rating).label("avg_rating"),
                func.count(Review.id).label("review_count")
            )
            .where(Review.reviewee_id == user_id)
        )
        review_row = review_stats.first()
        avg_rating = float(review_row.avg_rating or 0) if review_row else 0.0
        review_count = int(review_row.review_count or 0) if review_row else 0

        service_stats = await db.execute(
            select(func.avg(Service.price).label("avg_price"))
            .where(Service.worker_id == user_id)
        )
        service_row = service_stats.first()
        avg_service_price = float(service_row.avg_price or 0) if service_row else 0.0

        user.avg_rating = avg_rating
        user.average_rating = avg_rating
        user.total_reviews = review_count
        user.average_service_price = avg_service_price

        has_created_service, has_kyc_submission, has_kyc_approved = await WorkerService._get_profile_strength_inputs(db, user.id)
        completion_fields = WorkerService._completion_fields(
            user=user,
            has_created_service=has_created_service,
            has_kyc_submission=has_kyc_submission,
            has_kyc_approved=has_kyc_approved,
        )
        user.profile_completion_percentage = WorkerService._calculate_profile_completion(completion_fields)

        return user

    @staticmethod
    async def update_user_profile(db: AsyncSession, user_id: int, profile_data: WorkerProfileUpdate):
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        update_data = profile_data.model_dump(exclude_unset=True)

        # Handle nested structures for services and recent work
        if 'services_offered' in update_data and profile_data.services_offered is not None:
            user.services_offered = []
            for service in profile_data.services_offered:
                service_dict = service.model_dump()
                # Support both service_name and title fields for compatibility
                if 'title' in service_dict and 'service_name' not in service_dict:
                    service_dict['service_name'] = service_dict.pop('title')
                
                # Ensure only expected fields are passed to the model
                user.services_offered.append(
                    UserService(
                        service_name=service_dict.get("service_name"),
                        description=service_dict.get("description"),
                    )
                )
            del update_data["services_offered"]

        if 'recent_works' in update_data and profile_data.recent_works is not None:
            user.recent_works = []
            for work in profile_data.recent_works:
                work_dict = work.model_dump()
                work_dict['image_url'] = str(work_dict['image_url']) if work_dict.get('image_url') else None
                user.recent_works.append(RecentWork(**work_dict))
            del update_data["recent_works"]

        # Handle skills field (convert list to JSONB)
        if 'skills' in update_data and profile_data.skills is not None:
            user.skills = profile_data.skills
            del update_data["skills"]

        # Update direct fields from profile data
        for key, value in update_data.items():
            if hasattr(user, key) and value is not None:
                setattr(user, key, value)

        if profile_data.onboarding_step is not None:
            user.onboarding_step = profile_data.onboarding_step

        # Mark onboarding as complete
        user.is_onboarding_complete = True
        print(f'[WorkerService] Setting is_onboarding_complete=True for user_id: {user_id}')
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        print(f'[WorkerService] Worker profile updated. is_onboarding_complete={user.is_onboarding_complete}, user_id: {user_id}')

        # Create KYC submission if ID details are provided
        if (profile_data.id_type and
            profile_data.id_number and
            profile_data.id_image_url and
            profile_data.selfie_image_url):
            
            existing_kyc = await db.execute(
                select(KYCSubmission).where(KYCSubmission.user_id == user_id).where(KYCSubmission.status != "approved")
            )
            if not existing_kyc.scalar_one_or_none():
                submission = KYCSubmission(
                    user_id=user_id,
                    document_type=profile_data.id_type,
                    document_path=profile_data.id_image_url,
                    selfie_path=profile_data.selfie_image_url,
                    status="pending"
                )
                db.add(submission)
                await db.commit()

        # Re-query the user with all relationships to ensure the response model is satisfied
        return await WorkerService.get_user_profile(db, user_id)

    @staticmethod
    async def get_profile_completion_status(db: AsyncSession, user_id: int):
        """Get detailed profile completion status."""
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        has_created_service, has_kyc_submission, has_kyc_approved = await WorkerService._get_profile_strength_inputs(db, user_id)
        completion_fields = WorkerService._completion_fields(
            user=user,
            has_created_service=has_created_service,
            has_kyc_submission=has_kyc_submission,
            has_kyc_approved=has_kyc_approved,
        )
        percentage = WorkerService._calculate_profile_completion(completion_fields)
        completed, remaining = WorkerService._get_completion_fields(completion_fields)
        
        return {
            "completion_percentage": percentage,
            "fields_completed": completed,
            "fields_remaining": remaining
        }
