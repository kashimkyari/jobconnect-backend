from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update, func
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
from typing import List, Optional, Tuple
import math
import logging

from app.models.story import Story, StoryView, MediaType
from app.models.user import User
from app.models.service import Service
from app.models.job import Job
from app.models.review import Review
from app.models.enums import UserRole
from app.schemas.story import (
    StoryCreate,
    StoryResponse,
    StoryFeedItem,
    AvailabilitySlot,
    ViewerSummary,
    StoryWithViewers,
)
from app.services.file_service import FileService
from app.services.location_service import LocationService

logger = logging.getLogger(__name__)


def _utc_now_aligned(reference: Optional[datetime] = None) -> datetime:
    """
    Return current UTC time aligned to the datetime shape of `reference`.
    Some DB drivers may return timezone-naive values even for timezone-aware columns.
    """
    now_utc = datetime.now(timezone.utc)
    if reference is not None and reference.tzinfo is None:
        return now_utc.replace(tzinfo=None)
    return now_utc


class StoryService:
    """Service layer for story operations"""

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Great-circle distance between two coordinates in kilometers."""
        r = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(d_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        )
        return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    async def create_story(
        db: AsyncSession,
        worker_id: int,
        file_path: str,
        story_data: StoryCreate,
        creator_role: Optional[UserRole] = None,
        media_type: MediaType = MediaType.IMAGE,
        thumbnail_url: Optional[str] = None,
    ) -> StoryResponse:
        """
        Create a new story with media file.
        
        Args:
            db: Database session
            worker_id: ID of the worker creating the story
            file_path: Path to uploaded file
            story_data: Story metadata from request
            media_type: Type of media (image or video)
            thumbnail_url: Optional thumbnail for videos
            
        Returns:
            Created story object
            
        Raises:
            ValueError: If service not found or worker is not owner
        """
        if story_data.service_id and story_data.job_id:
            raise ValueError("Provide either service_id or job_id, not both")

        # If service_id provided, validate and fetch service
        service = None
        job = None
        service_name = story_data.service_name
        service_desc = story_data.service_desc
        price = story_data.price
        duration = story_data.duration

        if story_data.service_id:
            if creator_role != UserRole.WORKER:
                raise ValueError("Only workers can attach a service to a story")
            service_stmt = select(Service).where(
                and_(
                    Service.id == story_data.service_id,
                    Service.worker_id == worker_id,
                )
            )
            service = (await db.execute(service_stmt)).scalar_one_or_none()
            if not service:
                raise ValueError("Service not found or you don't have permission to use it")
            
            # Prefer denormalized values from request, fallback to service data
            service_name = story_data.service_name or service.name
            service_desc = story_data.service_desc or service.description
            price = story_data.price or service.price
            duration = story_data.duration  # Duration override from story, or None for service default
        elif story_data.job_id:
            if creator_role != UserRole.EMPLOYER:
                raise ValueError("Only employers can attach a job to a story")
            job_stmt = select(Job).where(
                and_(
                    Job.id == story_data.job_id,
                    Job.employer_id == worker_id,
                )
            )
            job = (await db.execute(job_stmt)).scalar_one_or_none()
            if not job:
                raise ValueError("Job not found or you don't have permission to use it")

            service_name = story_data.service_name or job.title
            service_desc = story_data.service_desc or job.description
            price = story_data.price or job.job_price
            duration = story_data.duration

        # Fetch worker to get availability
        worker_stmt = select(User).where(User.id == worker_id)
        worker = (await db.execute(worker_stmt)).scalar_one_or_none()
        if not worker:
            raise ValueError("Worker not found")

        # Get worker availability (mock for now if not set)
        availability = []
        if creator_role == UserRole.WORKER:
            availability = worker.worker_availability or [] if hasattr(worker, 'worker_availability') else []

        # Create story
        story = Story(
            worker_id=worker_id,
            service_id=story_data.service_id,
            job_id=story_data.job_id,
            media_url=file_path,
            media_type=media_type,
            thumbnail_url=thumbnail_url,
            caption=story_data.caption,
            service_name=service_name,
            service_desc=service_desc,
            price=price,
            duration=duration,
            worker_availability=availability,
            expires_at=Story.calculate_expiry(),
            view_count=0,
            is_active=True,
        )

        db.add(story)
        await db.flush()
        await db.refresh(story)

        return StoryResponse.model_validate(story)

    @staticmethod
    async def get_feed(
        db: AsyncSession,
        viewer_id: int,
        viewer_role: UserRole,
        skip: int = 0,
        limit: int = 20,
    ) -> List[StoryFeedItem]:
        """
        Get feed of non-expired stories, excluding seen ones, sorted by recency.
        
        Args:
            db: Database session
            viewer_id: ID of the user viewing the feed
            skip: Pagination skip
            limit: Pagination limit
            
        Returns:
            List of stories with enriched worker data
        """
        now = datetime.now(timezone.utc)

        target_role = UserRole.WORKER if viewer_role == UserRole.EMPLOYER else UserRole.EMPLOYER

        # Get all active, non-expired stories from opposite role
        stmt = (
            select(Story)
            .join(User, Story.worker_id == User.id)
            .where(
                and_(
                    Story.is_active == True,
                    Story.expires_at > now,
                    Story.worker_id != viewer_id,
                    User.role == target_role,
                )
            )
            .options(selectinload(Story.worker), selectinload(Story.views))
            .order_by(Story.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await db.execute(stmt)
        stories = result.unique().scalars().all()

        worker_ids = list({story.worker_id for story in stories if story.worker_id})
        review_count_map = {}
        if worker_ids:
            review_result = await db.execute(
                select(Review.reviewee_id, func.count(Review.id))
                .where(Review.reviewee_id.in_(worker_ids))
                .group_by(Review.reviewee_id)
            )
            review_count_map = {row[0]: int(row[1]) for row in review_result.all()}

        # Proximity filtering (same behavior for both viewer roles):
        # - If viewer has coordinates: include creators within the viewer's search_radius_km
        # - If viewer has no coordinates: return all opposite-role active stories
        viewer_stmt = select(User).where(User.id == viewer_id)
        viewer = (await db.execute(viewer_stmt)).scalar_one_or_none()
        if viewer and viewer.latitude is not None and viewer.longitude is not None:
            radius_km = float(LocationService.resolve_search_radius_km(user=viewer))
            prox_filtered = []
            for story in stories:
                creator = story.worker
                if not creator:
                    continue
                if creator.latitude is None or creator.longitude is None:
                    continue
                distance_km = StoryService._distance_km(
                    float(viewer.latitude),
                    float(viewer.longitude),
                    float(creator.latitude),
                    float(creator.longitude),
                )
                if distance_km <= radius_km:
                    prox_filtered.append(story)
            stories = prox_filtered

        # Get viewer's seen story IDs
        seen_stmt = select(StoryView.story_id).where(StoryView.viewer_id == viewer_id)
        seen_result = await db.execute(seen_stmt)
        seen_ids = set(row[0] for row in seen_result.fetchall())

        # Build feed items with worker info
        feed_items = []
        for story in stories:
            worker = story.worker
            worker_name = f"{worker.first_name or ''} {worker.last_name or ''}".strip()
            
            # Parse availability into AvailabilitySlot objects
            availability = []
            if story.worker_availability:
                try:
                    for avail in story.worker_availability:
                        if isinstance(avail, dict):
                            availability.append(AvailabilitySlot(**avail))
                except Exception as e:
                    logger.warning(f"Error parsing availability for story {story.id}: {e}")

            # Get service location if service relationship is loaded
            service_location = None
            if story.service and hasattr(story.service, 'city'):
                service_location = story.service.city
            
            item = StoryFeedItem(
                id=story.id,
                worker_id=story.worker_id,
                creator_role=worker.role.value if worker and worker.role else None,
                worker_name=worker_name,
                worker_avatar=worker.avatar_url,
                worker_rating=worker.reputation_score or 0.0,
                worker_review_count=review_count_map.get(story.worker_id, 0),
                worker_location=worker.city or worker.location or 'Location Unknown',
                media_url=story.media_url,
                media_type=story.media_type,
                thumbnail_url=story.thumbnail_url,
                caption=story.caption,
                service_id=story.service_id,
                job_id=story.job_id,
                service_name=story.service_name,
                service_desc=story.service_desc,
                service_location=service_location,
                price=story.price,
                duration=story.duration,
                availability=availability,
                seen=story.id in seen_ids,
                view_count=story.view_count,
                expires_at=story.expires_at,
                created_at=story.created_at,
            )
            feed_items.append(item)

        return feed_items

    @staticmethod
    async def mark_story_viewed(
        db: AsyncSession,
        story_id: int,
        viewer_id: int,
    ) -> Tuple[bool, int]:
        """
        Mark a story as viewed by a user and increment view count.
        Uses upsert to handle duplicate views gracefully.
        
        Args:
            db: Database session
            story_id: ID of the story
            viewer_id: ID of the viewer
            
        Returns:
            Tuple of (success, view_count)
            
        Raises:
            ValueError: If story not found or expired
        """
        # Verify story exists and is not expired
        story_stmt = select(Story).where(Story.id == story_id).with_for_update()
        story = (await db.execute(story_stmt)).scalar_one_or_none()
        
        if not story:
            raise ValueError("Story not found")
        
        if story.expires_at <= _utc_now_aligned(story.expires_at):
            raise ValueError("Story has expired")

        # Check if already viewed
        view_stmt = select(StoryView).where(
            and_(
                StoryView.story_id == story_id,
                StoryView.viewer_id == viewer_id,
            )
        )
        existing_view = (await db.execute(view_stmt)).scalar_one_or_none()

        # If not already viewed, create view record and increment count
        if not existing_view:
            view = StoryView(
                story_id=story_id,
                viewer_id=viewer_id,
                viewed_at=datetime.now(timezone.utc),
            )
            db.add(view)
            
            # Increment view count atomically
            story.view_count += 1

        await db.flush()
        await db.commit()

        return True, story.view_count

    @staticmethod
    async def delete_story(
        db: AsyncSession,
        story_id: int,
        user_id: int,
        is_admin: bool = False,
    ) -> bool:
        """
        Soft-delete a story (permission-checked).
        
        Args:
            db: Database session
            story_id: ID of the story
            user_id: ID of the user attempting deletion
            is_admin: Whether user is admin (can delete any story)
            
        Returns:
            True if deleted, False otherwise
            
        Raises:
            ValueError: If story not found or no permission
        """
        story_stmt = select(Story).where(Story.id == story_id).with_for_update()
        story = (await db.execute(story_stmt)).scalar_one_or_none()

        if not story:
            raise ValueError("Story not found")

        # Check permission: owner or admin
        if not is_admin and story.worker_id != user_id:
            raise ValueError("You don't have permission to delete this story")

        # Soft delete
        story.is_active = False
        await db.commit()

        return True

    @staticmethod
    async def get_worker_stories(
        db: AsyncSession,
        worker_id: int,
        skip: int = 0,
        limit: int = 20,
    ) -> List[StoryWithViewers]:
        """
        Get worker's own active, non-expired stories with viewer summaries.
        
        Args:
            db: Database session
            worker_id: ID of the worker
            skip: Pagination skip
            limit: Pagination limit
            
        Returns:
            List of stories with paginated viewer lists
        """
        now = datetime.now(timezone.utc)

        # Get active, non-expired stories only
        stmt = (
            select(Story)
            .where(
                and_(
                    Story.worker_id == worker_id,
                    Story.is_active == True,
                    Story.expires_at > now,
                )
            )
            .options(selectinload(Story.views).selectinload(StoryView.viewer))
            .order_by(Story.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await db.execute(stmt)
        stories = result.unique().scalars().all()

        # Build response with viewer summaries
        story_responses = []
        for story in stories:
            # Get top 5 viewers (paginated per story)
            viewers = []
            for view in sorted(story.views, key=lambda v: v.viewed_at, reverse=True)[:5]:
                viewer = view.viewer
                viewer_name = f"{viewer.first_name or ''} {viewer.last_name or ''}".strip()
                viewers.append(
                    ViewerSummary(
                        viewer_id=viewer.id,
                        viewer_name=viewer_name,
                        viewer_avatar=viewer.avatar_url,
                        viewed_at=view.viewed_at,
                    )
                )

            response = StoryWithViewers(
                id=story.id,
                media_url=story.media_url,
                media_type=story.media_type,
                job_id=story.job_id,
                caption=story.caption,
                service_name=story.service_name,
                view_count=story.view_count,
                viewers=viewers,
                created_at=story.created_at,
                expires_at=story.expires_at,
                is_active=story.is_active,
            )
            story_responses.append(response)

        return story_responses

    @staticmethod
    async def get_story_viewers(
        db: AsyncSession,
        story_id: int,
        user_id: int,
        is_admin: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[int, int, List[ViewerSummary]]:
        """
        Get paginated viewers for a story (owner/admin only).
        Returns (view_count, total_count, viewers).
        """
        safe_skip = max(0, int(skip or 0))
        safe_limit = max(1, min(int(limit or 50), 100))

        story_stmt = select(Story).where(Story.id == story_id)
        story = (await db.execute(story_stmt)).scalar_one_or_none()
        if not story:
            raise ValueError("Story not found")

        if not is_admin and story.worker_id != user_id:
            raise PermissionError("You don't have permission to view this story analytics")

        views_stmt = (
            select(StoryView)
            .where(StoryView.story_id == story_id)
            .options(selectinload(StoryView.viewer))
            .order_by(StoryView.viewed_at.desc())
            .offset(safe_skip)
            .limit(safe_limit)
        )
        views = (await db.execute(views_stmt)).scalars().all()

        viewers: List[ViewerSummary] = []
        for view in views:
            viewer = view.viewer
            if not viewer:
                continue
            viewer_name = f"{viewer.first_name or ''} {viewer.last_name or ''}".strip() or "Viewer"
            viewers.append(
                ViewerSummary(
                    viewer_id=viewer.id,
                    viewer_name=viewer_name,
                    viewer_avatar=viewer.avatar_url,
                    viewed_at=view.viewed_at,
                )
            )

        return int(story.view_count or 0), len(story.views or []), viewers

    @staticmethod
    async def expire_old_stories(db: AsyncSession) -> int:
        """
        Expire stories older than 24 hours (run as scheduled job).
        
        Args:
            db: Database session
            
        Returns:
            Number of stories expired
        """
        now = datetime.now(timezone.utc)
        
        stmt = (
            update(Story)
            .where(
                and_(
                    Story.expires_at < now,
                    Story.is_active == True,
                )
            )
            .values(is_active=False)
        )

        result = await db.execute(stmt)
        await db.commit()

        expired_count = result.rowcount
        logger.info(f"Expired {expired_count} old stories")

        return expired_count
