from typing import Optional
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.user import User, UserRole
from ..services.auth_service import get_current_user

async def get_subscription_status(
    current_user: User = Depends(get_current_user),
) -> bool:
    if current_user.role != UserRole.WORKER:
        return True

    grace_period = timedelta(days=3)
    now = datetime.utcnow()

    if current_user.subscription_expiry and current_user.subscription_expiry + grace_period >= now:
        return True
    
    return False

async def verify_active_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    FastAPI dependency that verifies if an employer has an active subscription.
    Includes a 3-day grace period after expiry.
    """
    if current_user.role != UserRole.EMPLOYER:
        return current_user
        
    # If subscription has expired but within grace period, allow access
    grace_period = timedelta(days=3)
    now = datetime.utcnow()
    
    if not current_user.subscription_status or (
        current_user.subscription_expiry 
        and current_user.subscription_expiry + grace_period < now
    ):
        raise HTTPException(
            status_code=402,
            detail="Active subscription required. Please subscribe to post jobs."
        )
    
    return current_user
