from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.block_service import BlockService
from app.database import get_db
from app.utils.security import get_current_user

router = APIRouter()

@router.post("/block/{worker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def block_worker(
    worker_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Block a worker from applying to the current employer's jobs."""
    if current_user.role != "employer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only employers can block workers.",
        )
    
    block_service = BlockService(db)
    await block_service.block_worker(employer_id=current_user.id, worker_id=worker_id)

@router.post("/unblock/{worker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_worker(
    worker_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unblock a worker."""
    if current_user.role != "employer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only employers can unblock workers.",
        )

    block_service = BlockService(db)
    await block_service.unblock_worker(employer_id=current_user.id, worker_id=worker_id)
