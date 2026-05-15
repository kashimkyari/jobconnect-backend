from .email_service import EmailService
from ..services import otp_service
from ..config import settings
from ..utils.logging import auth_logger
from ..database import async_session


def _get_role_value(role):
    """Safely extract role value whether it's an enum or string"""
    if role is None:
        return "user"
    # If it has a 'value' attribute (Enum), use that
    if hasattr(role, 'value'):
        return role.value
    # If it's already a string, return as-is
    if isinstance(role, str):
        return role
    # Fallback
    return str(role)


async def send_verification_email(user):
    """
    Sends a verification email to the user immediately (awaited).
    """
    auth_logger.info(
        "📧 Verification email sending...",
        user_id=user.id,
        email=user.email
    )
    async with async_session() as db:
        try:
            otp = await otp_service.generate_otp(db, user.id, "email_verification")
            auth_logger.info(
                "OTP generated for verification",
                user_id=user.id,
                email=user.email
            )
            verification_url = f"{settings.API_BASE_URL}/verify-account?otp={otp}&email={user.email}"
            email_service = EmailService()
            await email_service.send_email_verification(
                to_email=user.email,
                first_name=user.first_name or "User",
                otp=otp,
                verification_url=verification_url
            )
            auth_logger.info(
                "✅ Verification email sent immediately",
                user_id=user.id,
                email=user.email
            )
        except Exception as e:
            auth_logger.error(
                f"❌ Failed to send verification email: {str(e)}",
                user_id=user.id,
                email=user.email,
                error=str(e)
            )
            # Re-raise to propagate error to caller
            raise

async def send_password_reset_email(user):
    """
    Sends a password reset email to the user immediately (awaited).
    """
    auth_logger.info(
        "📧 Password reset email sending...",
        user_id=user.id,
        email=user.email
    )
    async with async_session() as db:
        try:
            otp = await otp_service.generate_otp(db, user.id, "password_reset")
            auth_logger.info(
                "OTP generated for password reset",
                user_id=user.id,
                email=user.email
            )
            reset_url = f"{settings.API_BASE_URL}/reset-password?otp={otp}&email={user.email}"
            email_service = EmailService()
            await email_service.send_password_reset(
                to_email=user.email,
                first_name=user.first_name or "User",
                otp=otp,
                reset_url=reset_url
            )
            auth_logger.info(
                "✅ Password reset email sent immediately",
                user_id=user.id,
                email=user.email
            )
        except Exception as e:
            auth_logger.error(
                f"❌ Failed to send password reset email: {str(e)}",
                user_id=user.id,
                email=user.email,
                error=str(e)
            )
            # Re-raise to propagate error to caller
            raise

async def send_welcome_email(user):
    """
    Sends a welcome email to a new user immediately (awaited).
    """
    role_value = _get_role_value(user.role)
    auth_logger.info(
        "📧 Welcome email sending...",
        user_id=user.id,
        email=user.email,
        role=role_value
    )
    try:
        email_service = EmailService()
        await email_service.send_welcome_email(
            to_email=user.email,
            first_name=user.first_name or "User",
            user_type=role_value,
            action_url=f"{settings.API_BASE_URL}/login"
        )
        auth_logger.info(
            "✅ Welcome email sent immediately",
            user_id=user.id,
            email=user.email
        )
    except Exception as e:
        auth_logger.error(
            f"❌ Failed to send welcome email: {str(e)}",
            user_id=user.id,
            email=user.email,
            error=str(e)
        )
        # Re-raise to propagate error to caller
        raise
