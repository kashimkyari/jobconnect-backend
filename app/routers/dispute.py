from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..models.user import User, UserRole
from ..schemas.dispute import DisputeCreate, DisputeUpdate, DisputeInDB, DisputeDetails
from ..services.dispute_service import DisputeService
from ..database import get_db
from ..utils.security import get_current_user, check_permissions

router = APIRouter()

@router.post("/", response_model=DisputeInDB, status_code=status.HTTP_201_CREATED)
async def create_dispute(
    dispute: DisputeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    dispute_service = DisputeService(db)
    new_dispute = await dispute_service.create_dispute(dispute.job_id, dispute, current_user.id)
    return new_dispute

@router.get("/my-disputes", response_model=List[DisputeInDB])
async def get_my_disputes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    dispute_service = DisputeService(db)
    disputes = await dispute_service.get_disputes_for_user(current_user.id)
    return disputes

@router.get("/job/{job_id}", response_model=List[DisputeInDB])
async def get_disputes_for_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    dispute_service = DisputeService(db)
    disputes = await dispute_service.get_disputes_by_job_id(job_id, current_user.id)
    return disputes

@router.get("/{dispute_id}", response_model=DisputeDetails)
async def get_dispute(
    dispute_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    dispute_service = DisputeService(db)
    dispute = await dispute_service.get_dispute_by_id(dispute_id)
    if not dispute:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found")
    
    # Check if the current user is part of the dispute or an admin
    if (current_user.id not in [dispute.claimant_id, dispute.defendant_id] and 
        current_user.role != UserRole.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this dispute")
        
    return dispute

from ..schemas.dispute import DisputeMessageCreate, DisputeMessageOut

@router.post("/{dispute_id}/message", response_model=DisputeMessageOut, status_code=status.HTTP_201_CREATED)
async def add_dispute_message(
    dispute_id: int,
    message: DisputeMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    dispute_service = DisputeService(db)
    new_message = await dispute_service.add_message(dispute_id=dispute_id, message_in=message, user_id=current_user.id)
    return new_message

@router.put("/{dispute_id}", response_model=DisputeInDB)
async def update_dispute(
    dispute_id: int,
    dispute_update: DisputeUpdate,
    current_user: User = Depends(check_permissions(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db)
):
    dispute_service = DisputeService(db)
    updated_dispute = await dispute_service.update_dispute(dispute_id, dispute_update, current_user.id)
    if not updated_dispute:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found")
    return updated_dispute

from fastapi import UploadFile, File
from ..services.file_service import FileService

@router.post("/upload")
async def upload_dispute_attachment(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload an attachment for a dispute.
    Returns the relative URL of the uploaded file.
    """
    file_service = FileService(db)
    
    # We allow images and videos for disputes
    allowed_types = {
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"
    }
    
    db_file = await file_service.upload_file(
        file=file,
        user_id=current_user.id,
        category="dispute_evidence",
        allowed_types=allowed_types
    )
    
    return {"url": db_file.file_path}
