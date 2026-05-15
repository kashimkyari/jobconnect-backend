from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Form,
    Query,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timezone
import logging

from app.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.story import MediaType, Story
from app.services.auth_service import get_current_user
from app.services.file_service import FileService
from app.services.story_service import StoryService
from app.schemas.story import (
    StoryCreate,
    StoryResponse,
    StoryFeedResponse,
    StoryViewResponse,
    WorkerStoriesResponse,
    StoryViewersResponse,
    ErrorResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stories", tags=["stories"])

# Allowed MIME types for story media
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_VIDEO_SIZE = 200 * 1024 * 1024  # 200 MB (backend compresses to ~5MB)


@router.post("/", response_model=StoryResponse, status_code=status.HTTP_201_CREATED)
async def create_story(
    file: UploadFile = File(..., description="Story media file"),
    service_id: Optional[int] = Form(None, description="ID of service to showcase"),
    job_id: Optional[int] = Form(None, description="ID of job to showcase (for employers)"),
    caption: Optional[str] = Form(None, max_length=500, description="Story caption"),
    service_name: str = Form(..., min_length=1, max_length=100, description="Name of service"),
    service_desc: Optional[str] = Form(None, max_length=500, description="Service description"),
    price: Optional[float] = Form(None, ge=0, description="Price override"),
    duration: Optional[int] = Form(None, ge=1, description="Duration in days"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a new story with media.
    
    - **file**: Image (JPEG/PNG/WebP, max 5MB) or Video (MP4/MOV, max 200MB - automatically compressed to ~5MB)
    - **service_id**: Optional worker service ID (workers only)
    - **job_id**: Optional employer job ID (employers only)
    - **service_name**: Required display title on story card (service/job title)
    """
    # Verify supported role
    if current_user.role not in (UserRole.WORKER, UserRole.EMPLOYER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workers or employers can create stories",
        )

    # Determine media type from content-type
    if file.content_type in ALLOWED_IMAGE_TYPES:
        media_type = MediaType.IMAGE
        max_size = MAX_IMAGE_SIZE
        allowed_types = ALLOWED_IMAGE_TYPES
    elif file.content_type in ALLOWED_VIDEO_TYPES:
        media_type = MediaType.VIDEO
        max_size = MAX_VIDEO_SIZE
        allowed_types = ALLOWED_VIDEO_TYPES
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Allowed: JPEG, PNG, WebP (images) or MP4, MOV (videos)",
        )

    try:
        # Upload file using FileService
        file_service = FileService(db)
        uploaded_file = await file_service.upload_file(
            file=file,
            user_id=current_user.id,
            category="story_media",
            allowed_types=allowed_types,
            max_size=max_size,
        )

        # Create story in database
        story_data = StoryCreate(
            service_id=service_id,
            job_id=job_id,
            caption=caption,
            service_name=service_name,
            service_desc=service_desc,
            price=price,
            duration=duration,
            media_type=media_type,
        )

        thumbnail_url = uploaded_file.file_path if media_type == MediaType.VIDEO else None
        story = await StoryService.create_story(
            db=db,
            worker_id=current_user.id,
            file_path=uploaded_file.file_path,
            story_data=story_data,
            creator_role=current_user.role,
            media_type=media_type,
            thumbnail_url=thumbnail_url,
        )

        logger.info(f"Story created: {story.id} by user {current_user.id} ({current_user.role})")
        return story

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error creating story: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create story",
        )


@router.get("/feed", response_model=StoryFeedResponse)
async def get_stories_feed(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(20, ge=1, le=100, description="Pagination limit"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get feed of active stories from the opposite role.
    
    - Employers see worker stories.
    - Workers see employer stories.
    - Excludes current user's own stories and already viewed status is included.
    
    - **skip**: How many stories to skip (pagination)
    - **limit**: How many stories to return (max 100)
    """
    # Verify supported role
    if current_user.role not in (UserRole.EMPLOYER, UserRole.WORKER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workers or employers can view story feed",
        )

    try:
        stories = await StoryService.get_feed(
            db=db,
            viewer_id=current_user.id,
            viewer_role=current_user.role,
            skip=skip,
            limit=limit,
        )

        return StoryFeedResponse(stories=stories)

    except Exception as e:
        logger.error(f"Error fetching story feed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch story feed",
        )


@router.get("/all", response_model=StoryFeedResponse)
async def get_all_stories(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=200, description="Pagination limit"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all active stories available to the current user (opposite role).

    - Employers see worker stories.
    - Workers see employer stories.
    - Excludes current user's own stories and includes seen status.

    - **skip**: How many stories to skip (pagination)
    - **limit**: How many stories to return (max 200)
    """
    if current_user.role not in (UserRole.EMPLOYER, UserRole.WORKER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workers or employers can view stories",
        )

    try:
        stories = await StoryService.get_feed(
            db=db,
            viewer_id=current_user.id,
            viewer_role=current_user.role,
            skip=skip,
            limit=limit,
        )

        return StoryFeedResponse(stories=stories)

    except Exception as e:
        logger.error(f"Error fetching all stories: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch stories",
        )


@router.post("/{story_id}/view", response_model=StoryViewResponse)
async def mark_story_viewed(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark a story as viewed by the current user.
    
    Increments view count and records the view timestamp.
    Safe to call multiple times (idempotent).
    
    - **story_id**: ID of the story to mark as viewed
    """
    try:
        success, view_count = await StoryService.mark_story_viewed(
            db=db,
            story_id=story_id,
            viewer_id=current_user.id,
        )

        return StoryViewResponse(
            success=success,
            view_count=view_count,
            message="Story marked as viewed",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error marking story viewed: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark story as viewed",
        )


@router.delete("/{story_id}", status_code=status.HTTP_200_OK)
async def delete_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete (soft-delete) a story.
    
    Only the story owner or admins can delete stories.
    Deleted stories are marked as inactive and won't appear in feeds.
    
    - **story_id**: ID of the story to delete
    """
    is_admin = current_user.role == UserRole.ADMIN
    
    try:
        await StoryService.delete_story(
            db=db,
            story_id=story_id,
            user_id=current_user.id,
            is_admin=is_admin,
        )

        logger.info(f"Story deleted: {story_id} by user {current_user.id}")
        return {"success": True, "message": "Story deleted"}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error deleting story: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete story",
        )


@router.get("/mine", response_model=WorkerStoriesResponse)
async def get_my_stories(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(20, ge=1, le=100, description="Pagination limit"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current worker's own stories.
    
    Returns active stories plus expired stories from last 7 days, ordered from oldest to newest.
    Includes viewer summaries (who viewed each story).
    
    - **skip**: How many stories to skip (pagination)
    - **limit**: How many stories to return (max 100)
    """
    # Verify supported role
    if current_user.role not in (UserRole.WORKER, UserRole.EMPLOYER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workers or employers can view their own stories",
        )

    try:
        stories = await StoryService.get_worker_stories(
            db=db,
            worker_id=current_user.id,
            skip=skip,
            limit=limit,
        )

        count_result = await db.execute(
            select(func.count(Story.id)).where(
                (Story.worker_id == current_user.id)
                & (Story.is_active == True)
                & (Story.expires_at > datetime.now(timezone.utc))
            )
        )
        total_count = int(count_result.scalar() or 0)

        return WorkerStoriesResponse(
            stories=stories,
            total_count=total_count,
        )

    except Exception as e:
        logger.error(f"Error fetching worker stories: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch your stories",
        )


@router.get("/{story_id}/viewers", response_model=StoryViewersResponse)
async def get_story_viewers(
    story_id: int,
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=100, description="Pagination limit"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get paginated viewers for a story (owner/admin only), including viewed timestamps.
    """
    is_admin = current_user.role == UserRole.ADMIN
    try:
        view_count, total_count, viewers = await StoryService.get_story_viewers(
            db=db,
            story_id=story_id,
            user_id=current_user.id,
            is_admin=is_admin,
            skip=skip,
            limit=limit,
        )
        return StoryViewersResponse(
            story_id=story_id,
            view_count=view_count,
            total_count=total_count,
            viewers=viewers,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching story viewers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch story viewers",
        )
