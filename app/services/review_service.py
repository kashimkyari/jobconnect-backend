from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from typing import List, Optional
import asyncio

from ..models.review import Review
from ..models.job import Job, JobStatus
from ..models.user import User
from ..models.job_application import JobApplication, ApplicationStatus
from ..models.service import Service
from ..models.booking import Booking
from ..models.enums import BookingStatus
from ..schemas.review import ReviewCreate, ReviewStats
from ..services.user_service import UserService
from ..services.notification_service import NotificationService
from ..schemas.notification import NotificationCreate
from ..models.notification import NotificationCategory
from .badge_service import BadgeService

class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_job_with_applications(self, job_id: int) -> Optional[Job]:
        query = (
            select(Job)
            .where(Job.id == job_id)
            .options(selectinload(Job.applications))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_review(self, review_data: ReviewCreate, reviewer_id: int) -> dict:
        """Create a review for either a job or a service.
        
        For service reviews:
        - Reviewer and reviewee must have a COMPLETED booking for the target service
        - Either party (employer or worker) can review the counterpart once completed
        """
        print(f"🔍 [ReviewService] Creating review - reviewer_id={reviewer_id}, job_id={review_data.job_id}, service_id={review_data.service_id}, reviewee_id={review_data.reviewee_id}")
        
        # Get reviewer user data
        reviewer = await self.db.get(User, reviewer_id)
        if not reviewer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reviewer not found"
            )

        normalized_comment = (review_data.comment or "").strip()
        if not normalized_comment:
            normalized_comment = f"Rated {float(review_data.rating):g} stars."
        
        # Handle SERVICE REVIEW
        if review_data.service_id:
            print(f"📦 [ReviewService] Processing service review for service_id={review_data.service_id}")
            
            # Get the service
            service = await self.db.get(Service, review_data.service_id)
            if not service:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Service not found"
                )
            
            print(f"✓ Service found: {service.name}, worker_id={service.worker_id}")
            
            # Role-specific target constraints:
            # - Employer review: shared review for service + worker (reviewee must be the worker who owns the service).
            # - Worker review: review must target the employer they completed booking with for this service.
            reviewer_role = str(reviewer.role.value if hasattr(reviewer.role, "value") else reviewer.role)
            if review_data.reviewee_id == reviewer_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You cannot review yourself."
                )

            if reviewer_role == "employer" and review_data.reviewee_id != service.worker_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Employer service reviews must target the worker who owns the service."
                )
            if reviewer_role == "worker":
                if reviewer_id != service.worker_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Only the worker who owns this service can review the employer for this service."
                    )
                if review_data.reviewee_id == service.worker_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Worker review after completion must target the employer."
                    )
            if reviewer_role not in {"employer", "worker"}:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only workers and employers can create service reviews."
                )
            
            print(
                f"🔐 [ReviewService] Verifying completed booking exists for service "
                f"{review_data.service_id} between reviewer {reviewer_id} and reviewee {review_data.reviewee_id}"
            )

            completed_booking_query = (
                select(Booking)
                .where(
                    Booking.service_id == review_data.service_id,
                    Booking.status == BookingStatus.COMPLETED,
                    (
                        (
                            (Booking.employer_id == reviewer_id) &
                            (Booking.worker_id == review_data.reviewee_id)
                        ) |
                        (
                            (Booking.worker_id == reviewer_id) &
                            (Booking.employer_id == review_data.reviewee_id)
                        )
                    )
                )
                .limit(1)
            )
            completed_booking_result = await self.db.execute(completed_booking_query)
            completed_booking = completed_booking_result.scalar_one_or_none()

            if not completed_booking:
                print(
                    f"❌ [ReviewService] No completed booking found for service "
                    f"{review_data.service_id} between users {reviewer_id} and {review_data.reviewee_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "You can only review after service completion. "
                        "No completed booking found for this service."
                    )
                )
            
            # Extra guard for worker-side reviews: reviewee must be the employer on completed booking.
            if reviewer_role == "worker" and completed_booking.employer_id != review_data.reviewee_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Worker review must target the employer from the completed booking."
                )

            print(
                f"✅ [ReviewService] Authorization verified: completed booking "
                f"{completed_booking.id} exists between reviewer {reviewer_id} and reviewee {review_data.reviewee_id}"
            )
            
            # Check if user has already reviewed this service
            existing_review = await self._get_existing_service_review(
                reviewer_id,
                review_data.reviewee_id,
                review_data.service_id
            )
            if existing_review:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You have already reviewed this service"
                )
            
            # Create service review
            review = Review(
                reviewer_id=reviewer_id,
                reviewee_id=review_data.reviewee_id,
                service_id=review_data.service_id,
                rating=review_data.rating,
                comment=normalized_comment
            )
            
            self.db.add(review)
            await self.db.flush()
            
            # Eagerly load the review
            query = (
                select(Review)
                .where(Review.id == review.id)
                .options(selectinload(Review.reviewee), selectinload(Review.service))
            )
            result = await self.db.execute(query)
            loaded_review = result.scalar_one()
            
            # Update user's reputation score
            await self._update_user_reputation(review_data.reviewee_id)
            
            # Commit all changes
            await self.db.commit()
            
            # Auto-award badges for the reviewed user (e.g., Top Rated badge)
            badge_service = BadgeService(self.db)
            try:
                award_result = await asyncio.wait_for(
                    badge_service.auto_award_badges(review_data.reviewee_id),
                    timeout=2.0,
                )
                if award_result['awarded']:
                    print(f"✅ [ReviewService] User earned badges on review: {[b['name'] for b in award_result['awarded']]}")
            except Exception as badge_error:
                # Badge side effects should never block review creation response
                print(f"⚠️ [ReviewService] Badge awarding skipped: {badge_error}")
            
            print(f"✅ [ReviewService] Service review created: ID={loaded_review.id}")
            
            # Build response
            response_data = {
                "id": loaded_review.id,
                "rating": loaded_review.rating,
                "comment": loaded_review.comment or normalized_comment,
                "service_id": loaded_review.service_id,
                "reviewer_id": loaded_review.reviewer_id,
                "reviewee_id": loaded_review.reviewee_id,
                "created_at": loaded_review.created_at,
                "updated_at": loaded_review.updated_at,
                "reviewer_name": f"{reviewer.first_name} {reviewer.last_name}",
                "reviewer_avatar": reviewer.avatar_url,
                "reviewee_name": f"{loaded_review.reviewee.first_name} {loaded_review.reviewee.last_name}",
                "reviewee_avatar": loaded_review.reviewee.avatar_url,
                "reviewee_email": loaded_review.reviewee.email,
                "service_name": loaded_review.service.name,
                "success": True,
                "message": "Service review submitted successfully"
            }
            
            return response_data
        
        # Handle JOB REVIEW (original logic)
        print(f"💼 [ReviewService] Processing job review for job_id={review_data.job_id}")
        
        job = await self.get_job_with_applications(review_data.job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
            
        # Enforce: job must be COMPLETED to allow reviews
        if job.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reviews can only be created for completed jobs. Current job status: {job.status.value}"
            )
            
        # Check if user is authorized to review this job
        if not (job.employer_id == reviewer_id or 
                any(app.worker_id == reviewer_id for app in job.applications)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to review this job"
            )
            
        # Check if user has already reviewed this job
        existing_review = await self._get_existing_review(
            reviewer_id,
            review_data.reviewee_id,
            review_data.job_id
        )
        if existing_review:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already reviewed this job"
            )
        
        # Create review
        review = Review(
            reviewer_id=reviewer_id,
            reviewee_id=review_data.reviewee_id,
            job_id=review_data.job_id,
            rating=review_data.rating,
            comment=normalized_comment
        )
        
        self.db.add(review)
        await self.db.flush()
        
        # Eagerly load the review with the reviewee for safe access
        query = (
            select(Review)
            .where(Review.id == review.id)
            .options(selectinload(Review.reviewee))
        )
        result = await self.db.execute(query)
        loaded_review = result.scalar_one()

        # Update user's reputation score (calculate but don't commit yet)
        await self._update_user_reputation(review_data.reviewee_id)
        await self.db.commit()
        
        # Build response with full context
        response_data = {
            "id": loaded_review.id,
            "rating": loaded_review.rating,
            "comment": loaded_review.comment or normalized_comment,
            "job_id": loaded_review.job_id,
            "reviewer_id": loaded_review.reviewer_id,
            "reviewee_id": loaded_review.reviewee_id,
            "created_at": loaded_review.created_at,
            "updated_at": loaded_review.updated_at,
            "reviewer_name": f"{reviewer.first_name} {reviewer.last_name}",
            "reviewer_avatar": reviewer.avatar_url,
            "reviewee_name": f"{loaded_review.reviewee.first_name} {loaded_review.reviewee.last_name}",
            "reviewee_avatar": loaded_review.reviewee.avatar_url,
            "reviewee_email": loaded_review.reviewee.email,
            "job_title": job.title,
            "job_description": job.description,
            "success": True,
            "message": "Review submitted successfully"
        }
        
        return response_data

    async def get_user_reviews(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 10
    ) -> List[dict]:
        query = (
            select(Review)
            .where((Review.reviewee_id == user_id) | (Review.reviewer_id == user_id))
            .options(
                selectinload(Review.reviewer),
                selectinload(Review.reviewee)
            )
            .order_by(desc(Review.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        reviews = result.scalars().all()

        # Manually construct dictionaries to match the updated ReviewInDB schema
        all_reviews = []
        for review in reviews:
            if not review.reviewer or not review.reviewee:
                continue

            review_data = {
                "id": review.id,
                "rating": review.rating,
                "comment": review.comment,
                "job_id": review.job_id,
                "reviewer_id": review.reviewer_id,
                "reviewee_id": review.reviewee_id,
                "created_at": review.created_at,
                "updated_at": review.updated_at,
                "reviewee_firstname": review.reviewee.first_name,
                "reviewee_lastname": review.reviewee.last_name,
                "reviewee_avatar": review.reviewee.avatar_url,
                "reviewer_firstname": review.reviewer.first_name,
                "reviewer_lastname": review.reviewer.last_name,
                "reviewer_avatar": review.reviewer.avatar_url,
            }
            all_reviews.append(review_data)
            
        return all_reviews

    async def get_job_reviews(self, job_id: int) -> List[Review]:
        query = (
            select(Review)
            .where(Review.job_id == job_id)
            .order_by(desc(Review.created_at))
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_reviews_given(self, user_id: int) -> List[Review]:
        query = (
            select(Review)
            .where(Review.reviewer_id == user_id)
            .options(
                selectinload(Review.reviewee),
                selectinload(Review.job),
                selectinload(Review.service)
            )
            .order_by(desc(Review.created_at))
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_reviews_received(self, user_id: int) -> List[Review]:
        query = (
            select(Review)
            .where(Review.reviewee_id == user_id)
            .options(selectinload(Review.reviewer))
            .order_by(desc(Review.created_at))
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_job_reviews_with_details(self, job_id: int) -> List[dict]:
        """Get all reviews for a job with full reviewer and reviewee details."""
        # First, get the job to determine employer_id for role assignment
        job = await self.db.get(Job, job_id)
        if not job:
            return []
        
        # Query reviews with loaded relationships
        query = (
            select(Review)
            .where(Review.job_id == job_id)
            .options(
                selectinload(Review.reviewer),
                selectinload(Review.reviewee)
            )
            .order_by(desc(Review.created_at))
        )
        result = await self.db.execute(query)
        reviews = result.scalars().all()
        
        # Build detailed review data with role context
        all_reviews = []
        for review in reviews:
            if not review.reviewer or not review.reviewee:
                continue
                
            review_data = {
                "id": review.id,
                "rating": review.rating,
                "comment": review.comment,
                "job_id": review.job_id,
                "reviewer_id": review.reviewer_id,
                "reviewer_name": f"{review.reviewer.first_name} {review.reviewer.last_name}",
                "reviewer_avatar": review.reviewer.avatar_url,
                "reviewer_role": "employer" if review.reviewer_id == job.employer_id else "worker",
                "reviewee_id": review.reviewee_id,
                "reviewee_name": f"{review.reviewee.first_name} {review.reviewee.last_name}",
                "reviewee_avatar": review.reviewee.avatar_url,
                "reviewee_role": "employer" if review.reviewee_id == job.employer_id else "worker",
                "created_at": review.created_at,
                "updated_at": review.updated_at,
            }
            all_reviews.append(review_data)
        
        return all_reviews

    async def get_user_review_stats(self, user_id: int) -> ReviewStats:
        # Get aggregate review statistics
        query = (
            select(
                func.count(Review.id).label("total_reviews"),
                func.avg(Review.rating).label("average_rating"),
                func.count(Review.id).filter(Review.rating == 5).label("five_star"),
                func.count(Review.id).filter(Review.rating == 4).label("four_star"),
                func.count(Review.id).filter(Review.rating == 3).label("three_star"),
                func.count(Review.id).filter(Review.rating == 2).label("two_star"),
                func.count(Review.id).filter(Review.rating == 1).label("one_star")
            )
            .where(Review.reviewee_id == user_id)
        )
        
        result = await self.db.execute(query)
        stats = result.fetchone()
        
        if not stats:
            return ReviewStats(
                total_reviews=0,
                average_rating=0.0,
                rating_distribution={
                    "5": 0, "4": 0, "3": 0, "2": 0, "1": 0
                }
            )
            
        return ReviewStats(
            total_reviews=stats.total_reviews,
            average_rating=float(stats.average_rating or 0),
            rating_distribution={
                "5": stats.five_star,
                "4": stats.four_star,
                "3": stats.three_star,
                "2": stats.two_star,
                "1": stats.one_star
            }
        )

    async def delete_review(self, review_id: int, user_id: int) -> bool:
        review = await self.db.get(Review, review_id)
        
        if not review or review.reviewer_id != user_id:
            return False
            
        await self.db.delete(review)
        await self.db.commit()
        
        # Update user's reputation score
        await self._update_user_reputation(review.reviewee_id)
        
        return True

    async def _get_existing_review(
        self,
        reviewer_id: int,
        reviewee_id: int,
        job_id: int
    ) -> Optional[Review]:
        query = select(Review).where(
            Review.reviewer_id == reviewer_id,
            Review.reviewee_id == reviewee_id,
            Review.job_id == job_id
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_existing_service_review(
        self,
        reviewer_id: int,
        reviewee_id: int,
        service_id: int
    ) -> Optional[Review]:
        """Check if reviewer has already reviewed this service from this worker."""
        query = select(Review).where(
            Review.reviewer_id == reviewer_id,
            Review.reviewee_id == reviewee_id,
            Review.service_id == service_id
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    async def _update_user_reputation(self, user_id: int):
        """Update user's reputation score based on their reviews."""
        try:
            # Calculate new reputation score
            query = (
                select(func.avg(Review.rating))
                .where(Review.reviewee_id == user_id)
            )
            result = await self.db.execute(query)
            new_score = result.scalar() or 0.0
            
            # Update user's reputation score directly without fetching
            # This avoids potential lock contention
            from sqlalchemy import update
            update_query = (
                update(User)
                .where(User.id == user_id)
                .values(reputation_score=new_score)
            )
            await self.db.execute(update_query)
            # Don't commit here - let the caller handle it
        except Exception as e:
            # Log but don't fail the review creation if reputation update fails
            print(f"Warning: Failed to update reputation for user {user_id}: {str(e)}")
