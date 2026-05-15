from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
from datetime import datetime, timedelta

from ..schemas.user import (
    UserUpdate,
    UserOut,
    UserRoleSwitch,
    UserProfile,
    JobPosterProfile,
    DailyClaimRequest,
    DailyClaimResponse,
    StreakHistoryResponse,
)
from ..schemas.auth import RoleSwitchResponse
from ..schemas.push_notification import PushTokenUpdate, PushTokenResponse
from ..schemas.recent_activity import RecentActivityOut
from ..models.user import User, UserRole
from ..services.user_service import UserService
from ..services.worker_service import WorkerService
from ..services.streak_service import StreakService
from ..services.admin_push_service import AdminPushService
from ..services.recent_activity_service import RecentActivityService
from ..services.profile_view_service import ProfileViewService
from ..services.subscription_service import SubscriptionService
from ..database import get_db
from fastapi import Request
from ..utils.security import get_current_user, check_permissions, create_access_token, create_refresh_token
from ..utils.logging import app_logger
from ..config import settings
from pydantic import BaseModel

router = APIRouter()

import asyncio

class ProfileCompletion(BaseModel):
    completion_percentage: int
    fields_completed: list[str]
    fields_remaining: list[str]

@router.get("/me", response_model=UserOut)
async def get_current_user_info(
    request: Request,
    delay: bool = False,
    current_user: User = Depends(get_current_user),
):
    db: AsyncSession = request.state.db
    app_logger.info(f"Fetching user info for user_id: {current_user.id}")

    if delay:
        app_logger.info("Delaying response for role switch verification...")
        await asyncio.sleep(2) # 2-second delay
    subscription_service = SubscriptionService(db)
    is_subscribed = await subscription_service.is_user_subscribed(current_user.id)
    
    app_logger.info(f"User subscription status: {is_subscribed}")
    
    user_out = UserOut.from_orm(current_user)
    user_out.is_subscribed = is_subscribed
    
    return user_out

@router.get("/public/avatar")
async def get_public_avatar(
    request: Request,
    email: str | None = None,
):
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email is required")

    db: AsyncSession = request.state.db

    normalized_email = email.strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email is required")

    result = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    user = result.scalars().first()

    if not user or not user.avatar_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found")

    return {"avatar_url": user.avatar_url}

@router.put("/me", response_model=UserOut)
async def update_user_info(
    request: Request,
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
):
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    updated_user = await user_service.update_user(current_user.id, user_update)
    return updated_user

@router.put("/me/profile", response_model=UserOut)
async def update_user_profile_info(
    request: Request,
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
):
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    updated_user = await user_service.update_user_profile(current_user.id, user_update)
    return updated_user

@router.post("/me/switch-role", response_model=RoleSwitchResponse)
async def switch_role(
    request: Request,
    role_data: UserRoleSwitch,
    current_user: User = Depends(get_current_user),
):
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    updated_user = await user_service.switch_user_role(current_user.id, role_data.role)
    
    # Generate new tokens with the updated role
    access_token = create_access_token(
        data={
            "sub": str(updated_user.id),
            "role": updated_user.role.value
        }
    )
    refresh_token = create_refresh_token(
        data={
            "sub": str(updated_user.id),
            "role": updated_user.role.value
        }
    )
    
    # Calculate token expiration
    expires_in = int(settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    
    return RoleSwitchResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
        user=updated_user
    )

@router.post("/me/avatar")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    avatar_url = await user_service.upload_avatar(current_user.id, file)
    return {"avatar_url": avatar_url}

@router.get("/me/wallet")
async def get_wallet_balance(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    wallet_data = await user_service.get_wallet_details(current_user.id)
    return wallet_data

@router.get("/me/profile-completion", response_model=ProfileCompletion)
async def get_my_profile_completion(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    db: AsyncSession = request.state.db
    if current_user.role == UserRole.WORKER:
        return await WorkerService.get_profile_completion_status(db, user_id=current_user.id)
    user_service = UserService(db)
    return await user_service.get_employer_profile_completion_status(current_user.id)

@router.post("/me/daily-claim", response_model=DailyClaimResponse)
async def claim_daily_streak(
    request: Request,
    claim_request: DailyClaimRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Claim daily streak reward. Can only be claimed once per day per user.
    
    The 24-hour window resets at midnight in the user's timezone.
    """
    db: AsyncSession = request.state.db
    
    # Refresh current_user to get latest data
    current_user = await db.get(User, current_user.id)
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    streak_service = StreakService(db)
    
    success, error_msg, result = await streak_service.process_daily_claim(
        current_user,
        client_timezone=claim_request.client_timezone
    )
    
    if not success:
        # Determine appropriate status code
        if "Already claimed" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_msg
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
    
    app_logger.info(
        f"Daily streak claimed for user_id: {current_user.id}, "
        f"streak_count: {result['streak_count']}, "
        f"credits_awarded: {result['credits_awarded']}"
    )
    
    return DailyClaimResponse(**result)


@router.get("/me/streak-history", response_model=StreakHistoryResponse)
async def get_streak_history(
    request: Request,
    days_back: int = 120,
    client_timezone: str = "UTC",
    current_user: User = Depends(get_current_user),
):
    """
    Get streak history by day for the authenticated user.
    """
    db: AsyncSession = request.state.db
    current_user = await db.get(User, current_user.id)
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    streak_service = StreakService(db)
    result = await streak_service.get_streak_history(
        current_user,
        days_back=days_back,
        client_timezone=client_timezone,
    )
    return StreakHistoryResponse(**result)

@router.get("/me/recent-activity", response_model=List[RecentActivityOut])
async def get_my_recent_activities(
    request: Request,
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 10,
):
    db: AsyncSession = request.state.db
    activity_service = RecentActivityService(db)
    activities = await activity_service.get_activities_for_user(
        user_id=current_user.id, skip=skip, limit=limit
    )
    return activities

@router.get("/workers", response_model=List[UserOut])
async def list_workers(
    request: Request,
    skip: int = 0,
    limit: int = 10,
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER, UserRole.ADMIN))
):
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    workers = await user_service.get_workers(skip, limit)
    return workers

@router.get("/employers", response_model=List[UserOut])
async def list_employers(
    request: Request,
    skip: int = 0,
    limit: int = 10,
    current_user: User = Depends(check_permissions(UserRole.WORKER, UserRole.ADMIN))
):
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    employers = await user_service.get_employers(current_user, skip, limit)
    return employers

@router.get("/search", response_model=List[UserOut])
async def search_users(
    request: Request,
    query: str,
    skip: int = 0,
    limit: int = 10,
    current_user: User = Depends(get_current_user)
):
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    users = await user_service.search_users(query, skip, limit)
    return users

@router.get("/{user_id}", response_model=UserProfile)
async def get_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user)
):
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    user_profile = await user_service.get_user_profile(user_id)
    if not user_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user_profile

@router.get("/job-poster/{user_id}", response_model=JobPosterProfile)
async def get_job_poster_profile(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user)
):
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    job_poster_profile = await user_service.get_job_poster_profile(user_id)
    if not job_poster_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job poster not found"
        )
    return job_poster_profile

@router.put("/{user_id}/verify", response_model=UserOut)
async def verify_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    verified_user = await user_service.verify_user(user_id)
    if not verified_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return verified_user

@router.put("/{user_id}/deactivate", response_model=UserOut)
async def deactivate_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(check_permissions(UserRole.ADMIN))
):
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    deactivated_user = await user_service.deactivate_user(user_id)
    if not deactivated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return deactivated_user


@router.get("/{user_id}/stats")
async def get_user_stats(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get user statistics (public profile)."""
    user_service = UserService(db)
    stats = await user_service.get_user_stats(user_id)
    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User statistics not found"
        )
    return stats

@router.post("/me/profile-viewed")
async def record_profile_view(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Record that current user viewed another user's profile."""
    profile_service = ProfileViewService(db)
    await profile_service.record_profile_view(user_id, current_user.id)
    return {"status": "recorded"}


@router.post("/me/push-token", response_model=PushTokenResponse)
async def update_push_token(
    request: Request,
    token_data: PushTokenUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update user's Expo push notification token"""
    db: AsyncSession = request.state.db
    admin_push_service = AdminPushService(db)
    
    success, reason = await admin_push_service.update_push_token(
        user_id=current_user.id,
        expo_push_token=token_data.expo_push_token,
        device_id=token_data.device_id,
        platform=token_data.platform,
        app_version=token_data.app_version,
    )
    
    if not success:
        detail = "Failed to update push token."
        if reason == "invalid_token_format":
            detail = "Invalid Expo push token format."
        elif reason == "missing_token":
            detail = "Push token is required."
        elif reason == "user_not_found":
            detail = "User not found."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )
    
    return PushTokenResponse(
        success=True,
        message="Push token updated successfully"
    )

# Location-based endpoints
@router.post("/me/location")
async def update_user_location(
    request: Request,
    location_data: dict,  # {"latitude": float, "longitude": float, "city": str, "state": str, "country": str, "search_radius_km": int}
    current_user: User = Depends(get_current_user),
):
    """Update user's location from GPS data"""
    from ..services.location_service import LocationService
    
    db: AsyncSession = request.state.db
    location_service = LocationService(db)
    
    required_fields = ["latitude", "longitude"]
    if not all(field in location_data for field in required_fields):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="latitude and longitude are required"
        )
    
    updated_user = await location_service.update_user_location(
        user_id=current_user.id,
        latitude=float(location_data["latitude"]),
        longitude=float(location_data["longitude"]),
        city=location_data.get("city"),
        state=location_data.get("state"),
        country=location_data.get("country"),
        search_radius_km=location_data.get("search_radius_km")
    )
    
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {
        "message": "Location updated successfully",
        "latitude": updated_user.latitude,
        "longitude": updated_user.longitude,
        "city": updated_user.city,
        "state": updated_user.state,
        "country": updated_user.country,
        "search_radius_km": updated_user.search_radius_km
    }


@router.get("/me/location")
async def get_user_location(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Get user's location data"""
    from ..schemas.user import LocationResponse
    
    if not current_user.latitude or not current_user.longitude:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User location not set"
        )
    
    return LocationResponse(
        latitude=current_user.latitude,
        longitude=current_user.longitude,
        city=current_user.city,
        state=current_user.state,
        country=current_user.country,
        search_radius_km=current_user.search_radius_km
    )


@router.put("/me/search-radius")
async def update_search_radius(
    request: Request,
    radius_data: dict,  # {"search_radius_km": int}
    current_user: User = Depends(get_current_user),
):
    """Update user's preferred search radius for location-based matching"""
    db: AsyncSession = request.state.db
    user_service = UserService(db)
    
    radius_km = radius_data.get("search_radius_km", 50)
    
    if radius_km < 1 or radius_km > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search radius must be between 1 and 500 km"
        )
    
    updated_user = await user_service.update_user(
        current_user.id,
        UserUpdate(search_radius_km=radius_km)
    )
    
    return {
        "message": "Search radius updated successfully",
        "search_radius_km": updated_user.search_radius_km
    }
