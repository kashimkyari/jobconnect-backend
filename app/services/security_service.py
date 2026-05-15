from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
import pyotp
from passlib.context import CryptContext

from ..models.user import User
from ..utils.security import get_password_hash, verify_password

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class SecurityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def set_transaction_pin(self, user_id: int, pin: str):
        """Set a 4-digit transaction pin for a user."""
        if not (pin.isdigit() and len(pin) == 4):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transaction pin must be a 4-digit number.",
            )

        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user.hashed_transaction_pin = get_password_hash(pin)
        await self.db.commit()

    async def verify_transaction_pin(self, user_id: int, pin: str) -> bool:
        """Verify a user's transaction pin."""
        user = await self.db.get(User, user_id)
        if not user or not user.hashed_transaction_pin:
            return False
        return verify_password(pin, user.hashed_transaction_pin)

    async def enable_2fa(self, user_id: int):
        """Enable 2FA for a user and return the OTP setup URI."""
        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if user.is_2fa_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="2FA is already enabled for this user.",
            )

        otp_secret = pyotp.random_base32()
        user.otp_secret = otp_secret
        await self.db.commit()

        totp = pyotp.TOTP(otp_secret)
        return {
            "otp_setup_uri": totp.provisioning_uri(name=user.email, issuer_name="JobConnect"),
            "otp_secret": otp_secret,
        }

    async def verify_2fa(self, user_id: int, otp_code: str) -> bool:
        """Verify a 2FA OTP code."""
        user = await self.db.get(User, user_id)
        if not user or not user.otp_secret:
            return False

        totp = pyotp.TOTP(user.otp_secret)
        is_valid = totp.verify(otp_code)

        if is_valid:
            if not user.is_2fa_enabled:
                user.is_2fa_enabled = True
                await self.db.commit()
            return True
        
        return False

    async def disable_2fa(self, user_id: int):
        """Disable 2FA for a user."""
        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user.is_2fa_enabled = False
        user.otp_secret = None
        await self.db.commit()
