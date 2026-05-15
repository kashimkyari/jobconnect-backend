from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.services.referral_service import ReferralService
from app.services.auth_service import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter()


@router.get("/referrals/code")
async def get_referral_code(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    referral_service = ReferralService(db)
    if not current_user.referral_code:
        return {"referral_code": await referral_service.generate_referral_code(current_user)}
    return {"referral_code": current_user.referral_code}


@router.get("/referrals")
async def get_referrals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    referral_service = ReferralService(db)
    return await referral_service.get_referrals_by_user(current_user.id)


@router.get('/referrals/validate')
async def validate_referral_code(code: str, db: AsyncSession = Depends(get_db)):
    """Validate a referral code (case-insensitive). Returns { valid: bool, referrer_id, referrer_name }"""
    if not code:
        return {"valid": False}
    normalized = code.strip().lower()
    result = await db.execute(select(User).where(func.lower(User.referral_code) == normalized))
    referrer = result.scalar_one_or_none()
    if not referrer:
        return {"valid": False}
    return {
        "valid": True,
        "referrer_id": referrer.id,
        "referrer_name": f"{referrer.first_name or ''} {referrer.last_name or ''}".strip()
    }
