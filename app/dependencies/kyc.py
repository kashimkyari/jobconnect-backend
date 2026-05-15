from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models.user import User
from ..services.auth_service import get_current_user
from ..services.kyc_service import KYCService

async def get_kyc_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> bool:
    kyc_service = KYCService(db)
    kyc_status = await kyc_service.get_verification_status(current_user.id)
    return kyc_status.is_verified
