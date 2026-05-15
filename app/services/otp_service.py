import random
import string
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.otp import OTP
from app.schemas.otp import OTPCreate
from app.config import settings

async def generate_otp(db: AsyncSession, user_id: str, purpose: str) -> str:
    otp_code = "".join(random.choices(string.digits, k=6))
    expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRATION_MINUTES)
    
    otp_create = OTPCreate(
        otp_code=otp_code,
        user_id=user_id,
        purpose=purpose,
        expires_at=expires_at
    )
    
    otp = OTP(**otp_create.dict())
    db.add(otp)
    await db.commit()
    await db.refresh(otp)
    
    return otp_code

async def verify_otp(db: AsyncSession, user_id: str, otp_code: str, purpose: str) -> bool:
    query = select(OTP).where(
        OTP.user_id == user_id,
        OTP.otp_code == otp_code,
        OTP.purpose == purpose,
        OTP.expires_at > datetime.utcnow()
    )
    result = await db.execute(query)
    otp = result.scalar_one_or_none()
    
    if otp:
        await db.delete(otp)
        await db.commit()
        return True
    
    return False
