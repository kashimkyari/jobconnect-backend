from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    Query
)
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from ..models.user import User
from ..schemas.file import FileInDB
from ..services.file_service import FileService
from ..database import get_db
from ..utils.security import get_current_user

router = APIRouter()

@router.post("/upload", response_model=FileInDB)
async def upload_file(
    file: UploadFile,
    category: str = Query(..., description="File category (e.g., avatar, job_attachment)"),
    reference_id: Optional[int] = Query(None, description="ID of related entity"),
    reference_type: Optional[str] = Query(None, description="Type of related entity"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    file_service = FileService(db)
    
    # Get allowed types for category
    allowed_types = FileService.get_allowed_types(category)
    if not allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file category: {category}"
        )
        
    uploaded_file = await file_service.upload_file(
        file=file,
        user_id=current_user.id,
        category=category,
        allowed_types=allowed_types,
        reference_id=reference_id,
        reference_type=reference_type
    )
    
    return uploaded_file

@router.get("/{file_id}", response_model=FileInDB)
async def get_file_info(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    file_service = FileService(db)
    file = await file_service.get_file(file_id, current_user.id, current_user.role == "ADMIN")
    
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
        
    return file

@router.get("/reference/{reference_type}/{reference_id}", response_model=List[FileInDB])
async def get_files_by_reference(
    reference_type: str,
    reference_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    file_service = FileService(db)
    files = await file_service.get_files_by_reference(
        reference_type=reference_type,
        reference_id=reference_id,
        user_id=current_user.id
    )
    return files

@router.get("/user/files", response_model=List[FileInDB])
async def get_user_files(
    category: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    file_service = FileService(db)
    files = await file_service.get_user_files(
        user_id=current_user.id,
        category=category,
        skip=skip,
        limit=limit
    )
    return files

@router.delete("/{file_id}")
async def delete_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    file_service = FileService(db)
    success = await file_service.delete_file(file_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
        
    return {"status": "file deleted successfully"}
