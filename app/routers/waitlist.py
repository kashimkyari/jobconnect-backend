from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.database import get_db
from app.schemas.waitlist import Waitlist, WaitlistCreate
from app.services import waitlist_service
from app.models.user import User, UserRole
from app.services.auth_service import get_current_user

router = APIRouter()

@router.post("/waitlist", response_model=Waitlist)
async def add_to_waitlist(waitlist_user: WaitlistCreate, db: AsyncSession = Depends(get_db)):
    return await waitlist_service.add_to_waitlist(db=db, waitlist_user=waitlist_user)

@router.get("/waitlist", response_model=List[Waitlist])
async def get_waitlist(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to access this resource")
    return await waitlist_service.get_waitlist_users(db=db)

@router.delete("/waitlist/{email}")
async def remove_from_waitlist(email: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to access this resource")
    return await waitlist_service.remove_from_waitlist(db=db, email=email)

