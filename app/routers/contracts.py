"""
Contracts Router - API endpoints for contract (job application) lifecycle.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from ..database import get_db
from ..models.user import User, UserRole
from ..utils.security import get_current_user, check_permissions
from ..services.contract_service import ContractService
from ..schemas.job_application import JobApplicationInDB
from ..utils.logging import StructuredLogger

router = APIRouter(prefix="/contracts", tags=["Contracts"])
logger = StructuredLogger(__name__)


@router.get("", response_model=List[JobApplicationInDB])
async def list_contracts(
    role: Optional[str] = None,  # "WORKER", "EMPLOYER"
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List contracts for the current user.
    
    Query params:
    - role: Filter by role (WORKER, EMPLOYER)
    - status: Filter by application status (pending, accepted, rejected, etc.)
    - skip, limit: Pagination
    """
    try:
        service = ContractService(db)
        contracts = await service.get_user_contracts(
            user_id=current_user.id,
            role=role,
            skip=skip,
            limit=limit
        )
        return contracts
    except Exception as e:
        logger.error(f"Error listing contracts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch contracts"
        )


@router.get("/{application_id}", response_model=JobApplicationInDB)
async def get_contract(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a single contract detail."""
    try:
        service = ContractService(db)
        contract = await service.get_contract(application_id, current_user.id)
        return contract
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching contract {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch contract"
        )


@router.get("/active", response_model=List[JobApplicationInDB])
async def list_active_contracts(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get active (in-progress) contracts for the current user.
    Automatically detects if user is worker or employer.
    """
    try:
        service = ContractService(db)
        role = "WORKER" if current_user.role == UserRole.WORKER else "EMPLOYER"
        contracts = await service.get_active_contracts(
            user_id=current_user.id,
            role=role,
            skip=skip,
            limit=limit
        )
        return contracts
    except Exception as e:
        logger.error(f"Error listing active contracts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch active contracts"
        )


@router.post("/{application_id}/activate", response_model=dict)
async def activate_contract(
    application_id: int,
    started_at: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Activate a contract (move job to IN_PROGRESS status).
    Called when worker starts work or employer confirms start.
    """
    try:
        service = ContractService(db)
        result = await service.activate_contract(
            application_id=application_id,
            current_user_id=current_user.id,
            started_at=started_at
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating contract {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate contract"
        )


@router.post("/{application_id}/mark-complete", response_model=dict)
async def mark_contract_complete(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark contract as complete from current user's perspective.
    
    - If WORKER marks complete: awaits employer confirmation
    - If EMPLOYER marks complete: also processes payment to worker
    - When both mark complete: job status becomes COMPLETED
    """
    try:
        service = ContractService(db)
        result = await service.mark_complete(
            application_id=application_id,
            current_user_id=current_user.id
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking contract complete {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark contract as complete"
        )


@router.post("/{application_id}/confirm-completion", response_model=dict)
async def confirm_contract_completion(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Confirm job completion (when other party marked complete first).
    This finalizes the job as COMPLETED and allows both parties to review.
    """
    try:
        service = ContractService(db)
        result = await service.confirm_completion(
            application_id=application_id,
            current_user_id=current_user.id
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming completion {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm completion"
        )


@router.get("/completed/list", response_model=dict)
async def get_completed_jobs(
    skip: int = 0,
    limit: int = 20,
    sort_by: str = "completed_at",  # "completed_at" or "rating"
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get completed jobs for the current user.
    
    Query params:
    - skip, limit: Pagination
    - sort_by: Sort by "completed_at" (newest first) or "rating"
    
    Response includes:
    - contract_id, job details, other party info, review status, payment status
    """
    try:
        service = ContractService(db)
        role = "WORKER" if current_user.role == UserRole.WORKER else "EMPLOYER"
        
        completed_jobs, total_count = await service.get_completed_jobs(
            user_id=current_user.id,
            role=role,
            skip=skip,
            limit=limit
        )

        return {
            "items": completed_jobs,
            "total": total_count,
            "skip": skip,
            "limit": limit
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching completed jobs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch completed jobs"
        )


@router.get("/stats", response_model=dict)
async def get_contract_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get contract statistics for the current user.
    
    Returns:
    - completed_jobs: count of completed jobs
    - total_jobs: total jobs worked on or posted
    - completion_rate: percentage of completed jobs
    """
    try:
        service = ContractService(db)
        role = "WORKER" if current_user.role == UserRole.WORKER else "EMPLOYER"
        
        stats = await service.get_completion_stats(
            user_id=current_user.id,
            role=role
        )
        return stats
    except Exception as e:
        logger.error(f"Error fetching contract stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch statistics"
        )
