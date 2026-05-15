from datetime import datetime
from typing import Optional
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models.user import User, UserRole
from ..models.job_application import JobApplication
from ..services.auth_service import get_current_user

APPLICATION_FEE = 100  # ₦100
FREE_APPLICATIONS_PER_MONTH = 3

async def verify_application_fee(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    """
    FastAPI dependency that verifies if a worker can apply for a job:
    - Checks free applications remaining
    - Verifies wallet balance for paid applications
    """
    if current_user.role != UserRole.WORKER:
        return current_user
        
    # Get the number of applications this month
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_applications = db.query(JobApplication).filter(
        JobApplication.worker_id == current_user.id,
        JobApplication.created_at >= start_of_month
    ).count()
    
    # If within free applications limit
    if monthly_applications < FREE_APPLICATIONS_PER_MONTH:
        return current_user
        
    # Check wallet balance for paid application
    if current_user.wallet_balance < APPLICATION_FEE:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient wallet balance. Please fund your wallet with at least ₦{APPLICATION_FEE}"
        )
    
    return current_user
