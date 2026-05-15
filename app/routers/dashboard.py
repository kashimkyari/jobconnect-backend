from typing import Union
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.auth_service import get_current_user
from app.models.user import User as UserModel
from app.schemas.employer_dashboard import EmployerDashboardSchema
from app.schemas.employer_dashboard import EmployerDashboardSchema
from app.services.employer_dashboard_service import get_employer_dashboard

router = APIRouter()

@router.get("/", response_model=EmployerDashboardSchema)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    if current_user.role == "employer":
        dashboard_data = await get_employer_dashboard(db, current_user.id)
        return dashboard_data
    else:
        raise HTTPException(status_code=403, detail="Invalid user role")
