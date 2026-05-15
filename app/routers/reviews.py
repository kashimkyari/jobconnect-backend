from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from ..models.user import User
from ..schemas.review import ReviewCreate, ReviewInDB, ReviewStats, ReviewWithUserDetails, ReviewCreateResponse
from ..services.review_service import ReviewService
from ..database import get_db, async_session
from ..utils.security import get_current_user
from ..utils.email_service import EmailService
from ..config import settings
from ..websocket_manager import manager as ws_manager
from ..utils.logging import app_logger

router = APIRouter()

@router.post("", response_model=ReviewCreateResponse)
async def create_review(
    review: ReviewCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new review for a completed job or completed service booking.
    
    Request body:
    - job_id: int (required for job reviews) OR service_id: int (required for service reviews)
    - reviewee_id: int (required - the user being reviewed)
    - rating: float 1-5 (required)
    - comment: str 1-500 chars (optional; fallback comment is generated if omitted)
    
    Returns: ReviewCreateResponse with full context including reviewer/reviewee info and job title
    """
    try:
        app_logger.info(
            f"Review endpoint: User {current_user.id} creating review "
            f"for job {review.job_id}, service {review.service_id}, "
            f"reviewee {review.reviewee_id}, rating {review.rating}"
        )
        
        # Create the review via service (fast - no notifications in this call)
        review_service = ReviewService(db)
        response_data = await review_service.create_review(review, current_user.id)
        
        app_logger.info(f"Review created successfully: ID {response_data.get('id')}")

        context_title = (
            response_data.get('job_title')
            or response_data.get('service_name')
            or 'service'
        )
        context_id = response_data.get('job_id') or response_data.get('service_id') or 0
        
        # Schedule background tasks (don't wait for these)
        # 1. Send email notification to reviewee
        background_tasks.add_task(
            send_review_notification_email,
            reviewee_email=response_data.get('reviewee_email', current_user.email),
            reviewee_name=response_data.get('reviewee_name', 'User'),
            reviewer_name=response_data.get('reviewer_name', 'Anonymous'),
            rating=int(response_data.get('rating', 0)),
            job_title=context_title,
            review_text=response_data.get('comment', ''),
        )

        # 2. Create in-app notification for reviewee
        background_tasks.add_task(
            create_review_notification,
            review_data=response_data,
        )

        # 3. Broadcast WebSocket event to reviewee
        background_tasks.add_task(
            ws_manager.broadcast_review_posted,
            contract_id=context_id,
            job_id=context_id,
            reviewer_id=current_user.id,
            target_user_id=response_data.get('reviewee_id', 0),
            rating=int(response_data.get('rating', 0)),
            reviewer_name=response_data.get('reviewer_name', ''),
            job_title=context_title
        )
        
        return response_data
        
    except HTTPException as http_err:
        app_logger.error(f"HTTP Error creating review: {http_err.detail}")
        raise http_err
        
    except Exception as e:
        app_logger.error(f"Unexpected error creating review: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create review. Please try again."
        )


# Background task helper functions
async def send_review_notification_email(
    reviewee_email: str,
    reviewee_name: str,
    reviewer_name: str,
    rating: int,
    job_title: str,
    review_text: Optional[str]
):
    """Send email notification about new review."""
    try:
        email_service = EmailService()
        await email_service.send_new_review_notification(
            to_email=reviewee_email,
            recipient_name=reviewee_name,
            reviewer_name=reviewer_name,
            rating=rating,
            review_date=datetime.now().strftime("%Y-%m-%d"),
            review_url=f"{settings.API_BASE_URL}/reviews",
            profile_url=f"{settings.API_BASE_URL}/profile",
            review_text=review_text
        )
        app_logger.info(f"Review notification email sent to {reviewee_email}")
    except Exception as e:
        app_logger.error(f"Failed to send review notification email: {str(e)}")


async def create_review_notification(review_data: dict):
    """Create in-app notification for review."""
    try:
        from ..services.notification_service import NotificationService
        from ..schemas.notification import NotificationCreate
        from ..models.notification import NotificationCategory

        reviewee_id = review_data.get("reviewee_id")
        if not reviewee_id:
            app_logger.warning("Skipping review notification: missing reviewee_id")
            return

        source_type = "service" if review_data.get("service_id") else "job"
        source_name = review_data.get("service_name") or review_data.get("job_title") or "completed work"
        created_at = review_data.get("created_at")
        created_at_str = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at or "")

        full_payload = {
            "review_id": review_data.get("id"),
            "reviewer_id": review_data.get("reviewer_id"),
            "reviewer_name": review_data.get("reviewer_name"),
            "reviewer_avatar": review_data.get("reviewer_avatar"),
            "reviewee_id": review_data.get("reviewee_id"),
            "reviewee_name": review_data.get("reviewee_name"),
            "reviewee_avatar": review_data.get("reviewee_avatar"),
            "rating": review_data.get("rating"),
            "comment": review_data.get("comment"),
            "source_type": source_type,
            "service_id": review_data.get("service_id"),
            "service_name": review_data.get("service_name"),
            "job_id": review_data.get("job_id"),
            "job_title": review_data.get("job_title"),
            "created_at": created_at_str,
            "review": {
                "id": review_data.get("id"),
                "reviewer_id": review_data.get("reviewer_id"),
                "reviewer_name": review_data.get("reviewer_name"),
                "reviewee_id": review_data.get("reviewee_id"),
                "reviewee_name": review_data.get("reviewee_name"),
                "rating": review_data.get("rating"),
                "comment": review_data.get("comment"),
                "service_id": review_data.get("service_id"),
                "service_name": review_data.get("service_name"),
                "job_id": review_data.get("job_id"),
                "job_title": review_data.get("job_title"),
                "created_at": created_at_str,
            },
        }
        action_payload = {k: v for k, v in full_payload.items() if v not in (None, "")}

        title = "You've Received a New Review"
        message = f"{review_data.get('reviewer_name', 'Someone')} left a review on {source_type}: {source_name}"

        async with async_session() as db:
            notification_service = NotificationService(db)
            await notification_service.create_notification(
                NotificationCreate(
                    user_id=reviewee_id,
                    title=title,
                    message=message,
                    category=NotificationCategory.REVIEWS_AND_REPUTATION,
                    action_screen="Reviews",
                    action_payload=action_payload,
                )
            )
        app_logger.info(f"Review notification created for user {reviewee_id}")
    except Exception as e:
        app_logger.error(f"Failed to create review notification: {str(e)}")

@router.get("/user/{user_id}", response_model=List[ReviewInDB])
async def get_user_reviews(
    user_id: int,
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    review_service = ReviewService(db)
    reviews = await review_service.get_user_reviews(user_id, skip, limit)
    return reviews

@router.get("/user/{user_id}/stats", response_model=ReviewStats)
async def get_user_review_stats(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    review_service = ReviewService(db)
    stats = await review_service.get_user_review_stats(user_id)
    return stats

@router.get("/job/{job_id}", response_model=List[ReviewWithUserDetails])
async def get_job_reviews(
    job_id: int,
    db: AsyncSession = Depends(get_db)
):
    review_service = ReviewService(db)
    reviews = await review_service.get_job_reviews_with_details(job_id)
    return reviews

@router.get("/given", response_model=List[dict])
async def get_reviews_given(
    limit: int = 20,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all reviews given by the current user with full context."""
    try:
        review_service = ReviewService(db)
        reviews = await review_service.get_reviews_given(current_user.id)
        app_logger.info(f"Found {len(reviews)} total reviews for user {current_user.id}")
        
        # Apply pagination
        paginated_reviews = reviews[skip:skip + limit]
        app_logger.info(f"Returning {len(paginated_reviews)} reviews after pagination (skip={skip}, limit={limit})")
        
        # Convert to dict with full details
        result = []
        for review in paginated_reviews:
            try:
                result.append({
                    'id': review.id,
                    'rating': float(review.rating),
                    'comment': review.comment,
                    'job_id': review.job_id,
                    'service_id': review.service_id,
                    'job_title': review.job.title if (review.job and hasattr(review.job, 'title')) else None,
                    'service_title': review.service.name if (review.service and hasattr(review.service, 'name')) else None,
                    'reviewer_id': review.reviewer_id,
                    'reviewee_id': review.reviewee_id,
                    'created_at': review.created_at.isoformat() if review.created_at else None,
                    'updated_at': review.updated_at.isoformat() if review.updated_at else None,
                    'reviewee': {
                        'id': review.reviewee.id if review.reviewee else None,
                        'full_name': f"{review.reviewee.first_name} {review.reviewee.last_name}".strip() if (review.reviewee and hasattr(review.reviewee, 'first_name')) else 'Unknown Worker',
                        'name': f"{review.reviewee.first_name} {review.reviewee.last_name}".strip() if (review.reviewee and hasattr(review.reviewee, 'first_name')) else 'Unknown Worker',
                        'profile_picture': review.reviewee.profile_picture if (review.reviewee and hasattr(review.reviewee, 'profile_picture')) else None,
                    } if review.reviewee else None,
                })
            except Exception as e:
                # Skip reviews that have loading issues but log them
                app_logger.warning(f"Error processing review {review.id}: {str(e)}")
                import traceback
                app_logger.warning(f"Traceback: {traceback.format_exc()}")
                continue
        
        app_logger.info(f"Successfully converted {len(result)} reviews to dicts")
        
        return result
    except Exception as e:
        app_logger.error(f"Error fetching reviews given: {str(e)}")
        return []

@router.get("/received", response_model=List[ReviewInDB])
async def get_reviews_received(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    review_service = ReviewService(db)
    reviews = await review_service.get_reviews_received(current_user.id)
    return reviews

@router.get("/service/{service_id}/can-review")
async def can_review_service(
    service_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Check if current user can review this service.
    Employer can review service/worker only after completed booking with this service.
    """
    try:
        from sqlalchemy.future import select
        from ..models.service import Service
        from ..models.booking import Booking
        from ..models.enums import BookingStatus
        from ..models.review import Review
        
        print(f"🔍 [can_review_service] Checking if user {current_user.id} can review service {service_id}")
        
        # Get the service
        service = await db.get(Service, service_id)
        if not service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found"
            )
        
        print(f"✓ Service found: {service.name}, worker_id={service.worker_id}")
        
        # Cannot review own service
        if service.worker_id == current_user.id:
            print(f"❌ User {current_user.id} is the service owner")
            return {
                "canReview": False,
                "hasReviewed": False,
                "reason": "You cannot review your own service"
            }
        
        # Only employers should review service/worker in this flow.
        current_role = str(current_user.role.value if hasattr(current_user.role, "value") else current_user.role)
        if current_role != "employer":
            return {
                "canReview": False,
                "hasReviewed": False,
                "reason": "Only employers can review services from this screen"
            }

        # Check if employer has completed booking with this worker on this service.
        query = (
            select(Booking)
            .where(
                Booking.service_id == service.id,
                Booking.employer_id == current_user.id,
                Booking.worker_id == service.worker_id,
                Booking.status == BookingStatus.COMPLETED
            )
            .limit(1)
        )
        result = await db.execute(query)
        completed_booking = result.scalar_one_or_none()
        
        if not completed_booking:
            print(f"❌ No completed booking found for employer {current_user.id} and worker {service.worker_id} on service {service.id}")
            return {
                "canReview": False,
                "hasReviewed": False,
                "reason": "You can review only after this service is completed."
            }

        # If reviewer already reviewed this worker for this service, lock review action.
        existing_review_query = (
            select(Review)
            .where(
                Review.reviewer_id == current_user.id,
                Review.reviewee_id == service.worker_id,
                Review.service_id == service.id
            )
            .limit(1)
        )
        existing_review_result = await db.execute(existing_review_query)
        existing_review = existing_review_result.scalar_one_or_none()
        if existing_review:
            return {
                "canReview": False,
                "hasReviewed": True,
                "reason": "You have already reviewed this service."
            }
        
        print(f"✅ User {current_user.id} can review service {service_id}")
        return {
            "canReview": True,
            "hasReviewed": False,
            "reason": "You are eligible to review this service"
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        app_logger.error(f"Error checking review eligibility: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error checking review eligibility"
        )

@router.delete("/{review_id}")
async def delete_review(
    review_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    review_service = ReviewService(db)
    deleted = await review_service.delete_review(review_id, current_user.id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found or not authorized to delete"
        )
    
    return {"status": "review deleted"}
