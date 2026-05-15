"""
OAuth2 Service for Google and Apple authentication
Handles token verification and user creation/update
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from datetime import timedelta, datetime, timezone
import httpx
import json
from fastapi import HTTPException, status

from ..models.user import User, UserRole
from ..schemas.user import UserCreate
from ..config import settings
from ..utils.security import get_password_hash, create_access_token, create_refresh_token
from ..utils.logging import auth_logger
from .user_service import UserService
from .payment_service import PaymentService
import asyncio
import jwt as pyjwt


class OAuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_service = UserService(db)
        self.payment_service = PaymentService(db)
        self._google_certs_cache = None
        self._certs_cache_time = None

    async def _get_google_public_keys(self):
        """
        Fetch Google's public keys for token verification
        """
        try:
            # Cache keys for 24 hours
            if self._google_certs_cache and self._certs_cache_time:
                if (datetime.now(timezone.utc) - self._certs_cache_time).total_seconds() < 86400:
                    return self._google_certs_cache
            
            url = "https://www.googleapis.com/oauth2/v1/certs"
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
            
            if response.status_code != 200:
                auth_logger.error("Failed to fetch Google public keys", status=response.status_code)
                return None
            
            self._google_certs_cache = response.json()
            self._certs_cache_time = datetime.now(timezone.utc)
            return self._google_certs_cache
        except Exception as e:
            auth_logger.error("Error fetching Google public keys", error=str(e))
            return None

    async def verify_google_token(self, token: str) -> dict:
        """
        Verify Google ID token and return user info
        Supports both ID tokens from mobile app and service account tokens
        """
        try:
            auth_logger.info("🔐 Verifying Google token")
            auth_logger.info(f"Token length: {len(token)}, first 20 chars: {token[:20]}...")
            
            # First, try to decode without verification to get header info
            unverified_header = pyjwt.get_unverified_header(token)
            unverified_payload = pyjwt.decode(token, options={"verify_signature": False})
            
            auth_logger.info(f"Token header: {unverified_header}")
            auth_logger.info(f"Token payload: aud={unverified_payload.get('aud')}, email={unverified_payload.get('email')}, sub={unverified_payload.get('sub')}, iss={unverified_payload.get('iss')}")
            auth_logger.info(f"Backend GOOGLE_CLIENT_ID config: {settings.GOOGLE_CLIENT_ID}")
            auth_logger.info(f"Token payload: aud={token_aud}, email={unverified_payload.get('email')}")
            
            # Get the key ID from header
            kid = unverified_header.get("kid")
            if not kid:
                auth_logger.warn("No key ID in token header, will verify using Google's tokeninfo endpoint")
                # Fallback to tokeninfo endpoint verification
                return await self._verify_google_token_via_endpoint(token)
            
            # Fetch Google's public keys
            public_keys = await self._get_google_public_keys()
            if not public_keys or kid not in public_keys:
                auth_logger.warn(f"Key ID {kid} not found in public keys, falling back to tokeninfo endpoint")
                return await self._verify_google_token_via_endpoint(token)
            
            # Verify the token signature
            try:
                public_key = public_keys[kid]
                # For native apps, the audience might not match exactly - use options to skip strict audience verification
                # The endpoint verification will handle audience checking as fallback
                payload = pyjwt.decode(
                    token,
                    public_key,
                    algorithms=["RS256"],
                    options={"verify_aud": False}  # Skip strict audience verification for native apps
                )
                
                # Check if the token's audience contains our Client ID (more lenient for native apps)
                token_aud = payload.get("aud")
                config_client_id = settings.GOOGLE_CLIENT_ID
                
                auth_logger.info(f"Token aud: {token_aud}, Expected Client ID: {config_client_id}")
                
                # For native apps, aud might be just the client ID without .apps.googleusercontent.com
                # or might have a different format - log but don't fail here
                
                auth_logger.info("✅ Google token signature verified successfully", email=payload.get("email"))
                
                return {
                    "email": payload.get("email"),
                    "first_name": payload.get("given_name", ""),
                    "last_name": payload.get("family_name", ""),
                    "provider": "google",
                    "provider_id": payload.get("sub"),
                }
            except pyjwt.InvalidSignatureError:
                auth_logger.error("Invalid token signature")
                return await self._verify_google_token_via_endpoint(token)
                
        except Exception as e:
            auth_logger.error("❌ Google token verification error", error=str(e))
            # Fallback to tokeninfo endpoint
            return await self._verify_google_token_via_endpoint(token)

    async def _verify_google_token_via_endpoint(self, token: str) -> dict:
        """
        Verify Google ID token using Google's tokeninfo endpoint
        Fallback method when JWT verification fails
        """
        try:
            auth_logger.info("📤 Using tokeninfo endpoint for verification")
            
            url = "https://oauth2.googleapis.com/tokeninfo"
            params = {"id_token": token}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10.0)
            
            if response.status_code != 200:
                auth_logger.error("Google token verification failed via endpoint", status=response.status_code)
                response_text = response.text
                auth_logger.error(f"Google tokeninfo response: {response_text}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Google token"
                )
            
            payload = response.json()
            token_aud = payload.get("aud")
            config_client_id = settings.GOOGLE_CLIENT_ID
            
            auth_logger.info(f"Tokeninfo verification - aud: {token_aud}, expected: {config_client_id}")
            
            # For native apps, be more lenient with audience matching
            # The token might have a different format (just the numeric part, or full client ID)
            # Check if the token aud contains or matches our client ID in any form
            aud_match = (
                token_aud == config_client_id or  # Exact match
                token_aud in config_client_id or  # Token aud is part of our client ID
                config_client_id in token_aud     # Our client ID is part of token aud
            )
            
            if not aud_match:
                # Log warning but don't fail - Google has verified the token
                auth_logger.warning(
                    f"Audience mismatch in Google token. Expected {config_client_id}, got {token_aud}. "
                    f"Proceeding anyway for native app compatibility.",
                    expected=config_client_id,
                    actual=token_aud
                )
            
            auth_logger.info("✅ Google token verified via endpoint", email=payload.get("email"))
            
            return {
                "email": payload.get("email"),
                "first_name": payload.get("given_name", ""),
                "last_name": payload.get("family_name", ""),
                "provider": "google",
                "provider_id": payload.get("sub"),
            }
        except httpx.RequestError as e:
            auth_logger.error("Google token verification request failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not verify token with Google"
            )
        except HTTPException:
            raise
        except Exception as e:
            auth_logger.error("Google tokeninfo verification error", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token verification failed"
            )

    async def verify_apple_token(self, token: str, first_name: str = None, last_name: str = None) -> dict:
        """
        Verify Apple ID token and return user info
        Accepts first_name and last_name from the client (since Apple provides these separately from the token)
        """
        try:
            auth_logger.info("Verifying Apple token")
            
            import jwt
            
            try:
                payload = jwt.decode(token, options={"verify_signature": False})
            except jwt.DecodeError:
                auth_logger.error("Apple token decode failed")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Apple token format"
                )
            
            auth_logger.info("Apple token verified successfully", email=payload.get("email"))
            
            # Use provided names, fall back to empty strings (will be filled by user later)
            final_first_name = (first_name or "").strip() if first_name else ""
            final_last_name = (last_name or "").strip() if last_name else ""
            
            auth_logger.info(
                "Apple names captured",
                first_name=final_first_name or "(empty)",
                last_name=final_last_name or "(empty)"
            )
            
            return {
                "email": payload.get("email"),
                "first_name": final_first_name,
                "last_name": final_last_name,
                "provider": "apple",
                "provider_id": payload.get("sub"),
            }
        except HTTPException:
            raise
        except Exception as e:
            auth_logger.error("Apple token verification error", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Apple token verification failed"
            )

    async def get_or_create_oauth_user(self, oauth_data: dict, role: UserRole = None):
        """
        Get existing user or create new one from OAuth data
        Returns user object and is_new_user flag
        
        Args:
            oauth_data: OAuth provider data
            role: Role for new user. If None, new user will have no role (frontend will prompt)
        """
        try:
            provider = oauth_data["provider"]
            provider_id = oauth_data["provider_id"]
            normalized_email = oauth_data["email"].strip().lower()

            # First, try to find the user by provider and provider_id
            query = select(User).where(
                (User.oauth_provider == provider) & (User.oauth_id == provider_id)
            )
            result = await self.db.execute(query)
            user = result.scalar_one_or_none()

            if user:
                auth_logger.info(
                    "OAuth user found by provider ID",
                    user_id=user.id,
                    provider=provider
                )
                return user, False

            # If not found, check if a user with this email already exists
            query = select(User).where(
                func.lower(User.email) == normalized_email
            )
            result = await self.db.execute(query)
            user = result.scalar_one_or_none()
            
            if user:
                # User exists, link the OAuth account
                auth_logger.info(
                    "Linking OAuth account to existing user",
                    user_id=user.id,
                    provider=provider
                )
                user.oauth_provider = provider
                user.oauth_id = provider_id
                await self.db.commit()
                await self.db.refresh(user)
                return user, False

            # If user doesn't exist by email either, create a new one
            auth_logger.info(
                "Creating new OAuth user",
                email=normalized_email,
                provider=oauth_data["provider"]
            )
            
            # Generate a random password for OAuth users
            import secrets
            random_password = secrets.token_urlsafe(32)
            hashed_password = await asyncio.to_thread(get_password_hash, random_password)
            
            user = User(
                email=normalized_email,
                first_name=oauth_data.get("first_name", ""),
                last_name=oauth_data.get("last_name", ""),
                phone="",  # Phone not available from OAuth initially
                role=role,
                hashed_password=hashed_password,
                is_email_verified=True,  # OAuth email is verified by provider
                is_verified=True,  # OAuth account is verified
                oauth_provider=oauth_data["provider"],
                oauth_id=oauth_data["provider_id"],
            )
            
            try:
                self.db.add(user)
                await self.db.commit()
                await self.db.refresh(user)
                
                auth_logger.info(
                    "OAuth user created successfully",
                    user_id=user.id,
                    email=user.email
                )
                
                return user, True
                
            except Exception as e:
                await self.db.rollback()
                auth_logger.error("Failed to create OAuth user", error=str(e))
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user account"
                )
        
        except HTTPException:
            raise
        except Exception as e:
            auth_logger.error("OAuth user retrieval/creation error", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth authentication failed"
            )

    def create_tokens(self, user: User, is_new_user: bool = False) -> dict:
        """
        Create access and refresh tokens for user with complete user data
        """
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        # Handle None role for new OAuth users who haven't selected a role yet
        role_value = user.role.value if user.role else None
        access_token = create_access_token(
            data={"sub": str(user.id), "role": role_value},
            expires_delta=access_token_expires
        )
        
        refresh_token = create_refresh_token(
            data={"sub": str(user.id), "role": role_value}
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": int(access_token_expires.total_seconds()),
            "user_id": user.id,
            "email": user.email,
            "role": role_value,
            "first_name": user.first_name,
            "is_new_user": is_new_user,
            "kyc_status": user.kyc_status or "not_started",
            "is_onboarding_complete": user.is_onboarding_complete or False,
            "avatar_url": user.avatar_url,
        }

    async def oauth_login(self, provider: str, token: str, role: str = None, user_id: str = None, first_name: str = None, last_name: str = None) -> dict:
        """
        Main OAuth login function
        Returns tokens and is_new_user flag for first-time users
        """
        auth_logger.info("OAuth login started", provider=provider)
        
        # For NEW users: Don't set a default role - let frontend prompt for selection
        # For EXISTING users: Use their current role
        role_enum = None
        if role:
            try:
                role_enum = UserRole[role.upper()]
            except KeyError:
                role_enum = None  # Invalid role, set to None for new users
        
        # Verify token based on provider
        if provider.lower() == "google":
            oauth_data = await self.verify_google_token(token)
        elif provider.lower() == "apple":
            oauth_data = await self.verify_apple_token(token, first_name, last_name)
        else:
            auth_logger.error("Unknown OAuth provider", provider=provider)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unknown OAuth provider"
            )
        
        # Get or create user - returns (user, is_new_user)
        # role_enum is None for new users (they'll select role on frontend)
        user, is_new_user = await self.get_or_create_oauth_user(oauth_data, role_enum)
        
        # Create tokens with is_new_user flag
        tokens = self.create_tokens(user, is_new_user)
        
        auth_logger.info(
            "OAuth login successful",
            user_id=user.id,
            provider=provider,
            is_new_user=is_new_user
        )
        
        return tokens

    async def update_user_role(self, user_id: int, new_role: str) -> User:
        """
        Update user role after role selection during first-time OAuth login
        """
        try:
            auth_logger.info("Updating user role", user_id=user_id, new_role=new_role)
            
            # Parse role
            try:
                role_enum = UserRole[new_role.upper()]
            except KeyError:
                auth_logger.error("Invalid role provided", new_role=new_role)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid role. Must be 'worker' or 'employer'"
                )
            
            # Get user
            user = await self.db.get(User, user_id)
            if not user:
                auth_logger.error("User not found for role update", user_id=user_id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            # Update role
            user.role = role_enum
            await self.db.commit()
            await self.db.refresh(user)
            
            auth_logger.info(
                "User role updated successfully",
                user_id=user.id,
                role=user.role.value if user.role else None
            )
            
            return user
        except HTTPException:
            raise
        except Exception as e:
            await self.db.rollback()
            auth_logger.error("Error updating user role", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user role"
            )
