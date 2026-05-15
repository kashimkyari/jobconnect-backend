from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.models.user import User
from app.services.security_service import SecurityService
from app.database import get_db
from app.utils.security import get_current_user

router = APIRouter()

class TransactionPinSetup(BaseModel):
    pin: str

class TwoFactorAuthVerification(BaseModel):
    otp_code: str

@router.post("/set-transaction-pin", status_code=status.HTTP_200_OK)
async def set_transaction_pin(
    pin_data: TransactionPinSetup,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Set a 4-digit transaction pin for the current user.
    """
    security_service = SecurityService(db)
    await security_service.set_transaction_pin(user_id=current_user.id, pin=pin_data.pin)
    return {"message": "Transaction pin set successfully."}

@router.post("/enable-2fa", status_code=status.HTTP_200_OK)
async def enable_2fa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Enable 2FA for the current user and get the OTP setup URI.
    """
    security_service = SecurityService(db)
    otp_data = await security_service.enable_2fa(user_id=current_user.id)
    return otp_data

@router.post("/verify-2fa", status_code=status.HTTP_200_OK)
async def verify_2fa(
    verification_data: TwoFactorAuthVerification,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify a 2FA OTP code.
    """
    security_service = SecurityService(db)
    is_valid = await security_service.verify_2fa(
        user_id=current_user.id, otp_code=verification_data.otp_code
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP code.",
        )
    return {"message": "2FA verified successfully."}

@router.post("/disable-2fa", status_code=status.HTTP_200_OK)
async def disable_2fa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Disable 2FA for the current user.
    """
    security_service = SecurityService(db)
    await security_service.disable_2fa(user_id=current_user.id)
    return {"message": "2FA disabled successfully."}
