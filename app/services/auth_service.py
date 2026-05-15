from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from datetime import datetime, timedelta, timezone
import asyncio
from fastapi import Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from ..models.user import User, UserRole
from ..models.token_blacklist import TokenBlacklist
from ..schemas.user import UserCreate, Token, TokenData
from ..utils.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_password_reset_token,
    create_email_verification_token,
)
from ..config import settings
from .notification_service import NotificationService
from ..schemas.notification import NotificationCreate
from ..models.notification import NotificationCategory
from ..database import get_db, async_session
from .user_service import UserService
from .referral_service import ReferralService
from app.models.referral import Referral, ReferralStatus
from ..utils.cache import get_cache, set_cache, delete_cache
from . import otp_service
from ..utils.logging import auth_logger
from ..utils.email_tasks import send_verification_email
from ..utils.email_service import EmailService
import json
from decimal import Decimal

oauth2_scheme = HTTPBearer()

async def get_current_user(request: Request, credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: int = int(payload.get("sub"))
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id, role=payload.get("role"))
    except (JWTError, ValueError):
        raise credentials_exception
    
    user = await request.state.db.get(User, token_data.user_id)
    if user is None:
        raise credentials_exception
    return user

async def get_current_user_ws(token: str | None = None) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception
    db = async_session()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: int = int(payload.get("sub"))
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id, role=payload.get("role"))
    except (JWTError, ValueError):
        await db.close()
        raise credentials_exception

    try:
        user = await db.get(User, token_data.user_id)
        if user is None:
            raise credentials_exception
        return user
    finally:
        await db.close()

async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user

async def get_current_worker(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.WORKER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires worker role"
        )
    return current_user

is_admin = get_admin_user

class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_service = UserService(db)

    async def register_user(self, user_data: UserCreate) -> User:
        # Normalize email for consistent storage
        normalized_email = user_data.email.strip().lower()
        
        # Check if user exists (case-insensitive)
        query = select(User).where(
            (func.lower(User.email) == normalized_email) |
            (User.phone == user_data.phone)
        )
        result = await self.db.execute(query)
        if result.scalar_one_or_none():
            raise ValueError("Email or phone already registered")
            
        # Create new user with normalized email
        hashed_password = await asyncio.to_thread(get_password_hash, user_data.password)
        user = User(
            email=normalized_email,  # Store normalized email
            phone=user_data.phone,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            role=user_data.role,
            hashed_password=hashed_password
        )
        
        try:
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)

            # If a referral code was supplied during registration, link the new user
            # to the referrer and create a Referral record.
            referral_code = getattr(user_data, 'referral_code', None)
            if referral_code:
                # Case-insensitive lookup for referral code; don't block registration if not found
                try:
                    ref_result = await self.db.execute(select(User).where(func.lower(User.referral_code) == referral_code.strip().lower()))
                    referrer = ref_result.scalar_one_or_none()
                    if referrer:
                        # Link referred user and create referral record
                        user.referred_by = referrer.id
                        self.db.add(user)
                        referral_entry = Referral(
                            referrer_id=referrer.id,
                            referred_id=user.id,
                            status=ReferralStatus.COMPLETED
                        )
                        self.db.add(referral_entry)
                        await self.db.commit()
                        await self.db.refresh(user)
                    else:
                        # Invalid code: log and continue (registration proceeds)
                        auth_logger.info("Referral code not found during registration, continuing without linking", referral_code=referral_code)
                except Exception as e:
                    # Non-fatal: don't block registration if referral linking fails
                    auth_logger.exception("Unexpected error linking referral during registration", error=str(e))
            
            auth_logger.info(
                "User registered successfully",
                user_id=user.id,
                email=user.email,
                role=user.role
            )
            
            # Create notification for admin
            notification_service = NotificationService(self.db)
            admin_ids = await self.user_service.get_admin_user_ids()
            for admin_id in admin_ids:
                await notification_service.create_notification(
                    NotificationCreate(
                        user_id=admin_id,
                        title="New User Registration",
                        message=f"A new user has registered: {user.email} ({user.role.value})",
                        category=NotificationCategory.TRUST_AND_SAFETY,
                        action_screen="UserDetails",
                        action_payload={"user_id": user.id}
                    )
                )

            # Grant referral reward if applicable
            referral_service = ReferralService(self.db)
            await referral_service.grant_signup_reward(user)

            # Send welcome email
            # await send_welcome_email(user, self.db)

            return user
        except IntegrityError as e:
            await self.db.rollback()
            auth_logger.error(
                "Registration failed - IntegrityError",
                email=normalized_email,
                error=str(e)
            )
            raise ValueError("Email or phone already registered")

    async def authenticate_user(
        self,
        email: str,
        password: str,
        role: str | None = None,
    ) -> User | None:
        try:
            normalized_email = email.strip().lower()
            cache_key = f"user:{normalized_email}"
            
            # Check cache first
            cached_user = await get_cache(cache_key)
            if cached_user:
                user_data = json.loads(cached_user)
                # Backwards compatibility for cached data
                if 'onboarding_completed' in user_data:
                    user_data['is_onboarding_complete'] = user_data.pop('onboarding_completed')
                # Create a user object from the cached data
                user = User(**user_data)
                password_verified = await asyncio.to_thread(verify_password, password, user.hashed_password)
                if password_verified:
                    # If role is provided, ensure it matches the cached user's role
                    # The user.role from a cached object might be a string, so we compare directly
                    if role and user.role != role:
                        pass  # Don't return cached user if role doesn't match
                    else:
                        return user

            # If not in cache or password is wrong, query the database
            # Build the query
            query = select(User).where(
                (func.lower(User.email) == normalized_email) | (User.phone == email)
            )
            if role:
                query = query.where(User.role == UserRole[role.upper()])
            
            result = await self.db.execute(query)
            user = result.scalar_one_or_none()
            
            if not user:
                auth_logger.warning(
                    "Login attempt - user not found",
                    email=normalized_email,
                    phone=email
                )
                return None

            # Check if account is locked
            if user.lockout_until and user.lockout_until > datetime.now(timezone.utc):
                auth_logger.warning(
                    "Login attempt on locked account",
                    user_id=user.id,
                    lockout_until=user.lockout_until
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Account locked. Try again after {user.lockout_until.strftime('%Y-%m-%d %H:%M:%S')} UTC."
                )
            
            # Note: Users can now login via either email/password OR OAuth if both are set
            # This provides better UX - they can use whichever method they prefer
            
            if not user.is_verified:
                auth_logger.info(
                    "Login attempt on unverified account",
                    user_id=user.id,
                    email=user.email
                )
                
                # Send email verification with OTP immediately (awaited)
                auth_logger.info(
                    "Sending verification email immediately...",
                    user_id=user.id,
                    email=user.email
                )
                try:
                    await send_verification_email(user)
                    auth_logger.info(
                        "✅ Verification email sent successfully",
                        user_id=user.id,
                        email=user.email
                    )
                except Exception as email_error:
                    auth_logger.warning(
                        "⚠️ Email sending failed, but continuing with login response",
                        user_id=user.id,
                        email=user.email,
                        error=str(email_error)
                    )
                
                # Raise custom exception for unverified account
                raise ValueError(f"UNVERIFIED:{user.email}")
                
            password_verified = await asyncio.to_thread(verify_password, password, user.hashed_password)
            if not password_verified:
                auth_logger.warning(
                    "Login attempt with incorrect password",
                    user_id=user.id,
                    email=user.email
                )
                if user.failed_login_attempts is None:
                    user.failed_login_attempts = 0
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= 5:
                    user.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                    user.failed_login_attempts = 0  # Reset after locking
                    
                    auth_logger.warning(
                        "Account locked due to multiple failed attempts",
                        user_id=user.id,
                        email=user.email
                    )
                    
                    # Send lockout email
                    lockout_time_str = user.lockout_until.strftime('%Y-%m-%d %H:%M:%S')
                    # send_lockout_email_task.delay(user.email, lockout_time_str)

                    # Create in-app notification
                    notification_service = NotificationService(self.db)
                    await notification_service.create_notification(
                        NotificationCreate(
                            user_id=user.id,
                            title="Account Locked",
                            message=f"Your account has been locked due to multiple failed login attempts. Please try again after {lockout_time_str} UTC.",
                            category=NotificationCategory.TRUST_AND_SAFETY
                        )
                    )
                    
                await self.db.commit()
                return None
                
            # Reset failed login attempts on successful login
            user.failed_login_attempts = 0
            user.lockout_until = None
            
            # Build cache data BEFORE commit to avoid lazy-loading in async context after commit
            user_data = {c.name: getattr(user, c.name) for c in user.__table__.columns}
            
            await self.db.commit()
            
            auth_logger.info(
                "User authenticated successfully",
                user_id=user.id,
                email=user.email,
                role=user.role
            )
            
            # Cache the user data (convert datetime and Decimal objects to string)
            for key, value in user_data.items():
                if isinstance(value, datetime):
                    user_data[key] = value.isoformat()
                elif isinstance(value, Decimal):
                    user_data[key] = float(value)
            await set_cache(cache_key, json.dumps(user_data))
            
            return user
        except HTTPException:
            # Re-raise HTTPException as-is (401, 403, etc.)
            raise
        except ValueError as e:
            # Re-raise ValueError for custom handling in router (e.g., UNVERIFIED accounts)
            raise
        except Exception as e:
            auth_logger.exception(
                "An unexpected error occurred during user authentication",
                email=email,
                role=role
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred during login."
            )

    def create_access_token(self, data: dict, expires_delta: timedelta | None = None) -> str:
        return create_access_token(data, expires_delta)

    def create_refresh_token(self, data: dict) -> str:
        return create_refresh_token(data)

    async def refresh_tokens(self, refresh_token: str, ip_address: str = "", user_agent: str = "") -> Token | None:
        from ..models.user_session import UserSession
        import hashlib
        
        # Check if the token is blacklisted
        blacklist_query = select(TokenBlacklist).where(TokenBlacklist.token == refresh_token)
        result = await self.db.execute(blacklist_query)
        if result.scalar_one_or_none():
            return None

        try:
            # Verify refresh token and get user data
            from jose import jwt
            payload = jwt.decode(
                refresh_token,
                settings.JWT_REFRESH_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            user_id = int(payload.get("sub"))
            user_role = payload.get("role")
            
            # Check if user exists
            user = await self.db.get(User, user_id)
            if not user:
                return None
                
            # Verify the session
            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            session_query = select(UserSession).where(
                UserSession.refresh_token_hash == token_hash,
                UserSession.is_active == True
            ).with_for_update()
            result = await self.db.execute(session_query)
            session = result.scalar_one_or_none()
            
            if session:
                session.is_active = False # Invalidate the use of this specific token
            
            # Create new tokens
            access_token = self.create_access_token(
                data={"sub": str(user_id), "role": user_role},
                expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            )
            new_refresh_token = self.create_refresh_token(
                data={"sub": str(user_id), "role": user_role}
            )
            
            # Create new session for the newly generated refresh token
            await self.create_user_session(
                user_id=user_id,
                refresh_token=new_refresh_token,
                ip_address=ip_address or (session.ip_address if session else ""),
                user_agent=user_agent or (session.user_agent if session else ""),
                device_name=session.device_name if session else "",
                device_model=session.device_model if session else "",
                device_brand=session.device_brand if session else "",
                device_type=session.device_type if session else "",
                os_name=session.os_name if session else "",
                os_version=session.os_version if session else ""
            )
            
            return {
                "access_token": access_token,
                "refresh_token": new_refresh_token,
                "token_type": "bearer"
            }
        except Exception:
            return None

    async def logout(self, refresh_token: str) -> None:
        try:
            from ..models.user_session import UserSession
            import hashlib
            
            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            session_query = select(UserSession).where(UserSession.refresh_token_hash == token_hash)
            result = await self.db.execute(session_query)
            session = result.scalar_one_or_none()
            if session:
                session.is_active = False

            payload = jwt.decode(
                refresh_token,
                settings.JWT_REFRESH_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                options={"verify_exp": False} # We want to blacklist even if expired
            )
            user_id = int(payload.get("sub"))
            user = await self.db.get(User, user_id)
            if user:
                delete_cache(f"user:{user.email}")

            expires_at = datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc)
            
            blacklist_entry = TokenBlacklist(
                token=refresh_token,
                expires_at=expires_at
            )
            self.db.add(blacklist_entry)
            await self.db.commit()
        except (JWTError, ValueError):
            # If the token is invalid, we can't blacklist it, but it's also unusable.
            # We can just ignore it.
            pass

    async def request_password_reset(self, email: str):
        await self.request_otp(email, "password_reset")

    async def request_email_verification(self, email: str):
        await self.request_otp(email, "email_verification")

    async def request_otp(self, email: str, reason: str):
        user = await self._get_user_by_email(email)
        if not user:
            raise ValueError("User not found")

        otp = await otp_service.generate_otp(self.db, user.id, reason)

        if reason == "email_verification":
            # await send_verification_email(user, self.db)
            pass
        elif reason == "password_reset":
            # await send_password_reset_email(user, self.db)
            pass
        else:
            # Handle unknown reasons if necessary
            return

    async def verify_otp(self, email: str, otp: str, reason: str) -> str | None:
        user = await self._get_user_by_email(email)
        if not user:
            return None

        is_valid = await otp_service.verify_otp(self.db, user.id, otp, reason)
        if is_valid:
            if reason == "password_reset":
                return create_password_reset_token(data={"sub": str(user.id)})
            elif reason == "email_verification":
                return create_email_verification_token(data={"sub": str(user.id)})
        return None

    async def reset_password(self, reset_token: str, new_password: str) -> bool:
        try:
            payload = jwt.decode(
                reset_token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            if payload.get("scope") != "password_reset":
                auth_logger.warning("Password reset token with invalid scope", token=reset_token)
                return False

            user_id = int(payload.get("sub"))
            user = await self.db.get(User, user_id)
            if not user:
                auth_logger.warning("Password reset token for non-existent user", user_id=user_id)
                return False

            user.hashed_password = await asyncio.to_thread(get_password_hash, new_password)
            await self.db.commit()
            delete_cache(f"user:{user.email}")
            auth_logger.info("Password reset successfully", user_id=user_id)
            return True
        except jwt.ExpiredSignatureError:
            auth_logger.warning("Expired password reset token used", token=reset_token)
            return False
        except JWTError as e:
            auth_logger.error("Invalid password reset token", token=reset_token, error=str(e))
            return False

    async def verify_account(self, email: str, token: str) -> bool:
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            if payload.get("scope") != "email_verification":
                return False

            user_id = int(payload.get("sub"))
            user = await self.db.get(User, user_id)
            if not user or user.email != email:
                return False

            user.is_verified = True
            await self.db.commit()
            delete_cache(f"user:{email}")
            return True
        except JWTError:
            return False

    async def get_user_role_by_email(self, email: str) -> str | None:
        normalized_email = email.strip().lower()
        query = select(User.role).where(func.lower(User.email) == normalized_email)
        result = await self.db.execute(query)
        role = result.scalar_one_or_none()
        if role:
            return role.value
        return None

    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
        hashed_password = await asyncio.to_thread(get_password_hash, user_data.password)
        user = User(
            email=user_data.email,
            phone=user_data.phone,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            role=user_data.role,
            hashed_password=hashed_password
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
        query = select(User).where(User.email == email)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _get_user_by_email(self, email: str) -> User | None:
        return await self.get_user_by_email(self.db, email)

    async def update_user(self, user_id: int, data: dict) -> User:
        user = await self.db.get(User, user_id)
        for key, value in data.items():
            setattr(user, key, value)
        await self.db.commit()
        await self.db.refresh(user)
        delete_cache(f"user:{user.email}")
        return user

    async def create_user_session(
        self, user_id: int, refresh_token: str, ip_address: str, user_agent: str, 
        device_name: str = "", device_model: str = "", device_brand: str = "", 
        device_type: str = "", os_name: str = "", os_version: str = ""
    ):
        from ..models.user_session import UserSession
        from ..utils.device_utils import parse_user_agent, get_location_from_ip
        import hashlib
        
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        device_info = parse_user_agent(user_agent, device_name, device_type)
        location = await get_location_from_ip(ip_address)
        
        # We need an expiry for the session, defaults to 30 days
        days = getattr(settings, "REFRESH_TOKEN_EXPIRE_DAYS", 30)
        expires_at = datetime.now(timezone.utc) + timedelta(days=days)
        
        session = UserSession(
            user_id=user_id,
            refresh_token_hash=token_hash,
            device_name=device_info.get("name", device_name),
            device_model=device_model,
            device_brand=device_brand,
            device_type=device_info.get("type", device_type),
            os_name=os_name,
            os_version=os_version,
            ip_address=ip_address,
            location=location,
            user_agent=user_agent,
            is_active=True,
            expires_at=expires_at
        )
        self.db.add(session)
        await self.db.commit()
        return session
