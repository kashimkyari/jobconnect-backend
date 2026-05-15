from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta

from ..schemas.user import UserCreate, Token, UserOut, UserUpdate
from ..schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    LoginResponse,
    UserDataResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    VerifyAccountRequest,
    ResendOTPRequest,
    VerifyOTPRequest,
    VerifyOTPResponse,
    GetRoleRequest,
    GetRoleResponse,
    OAuthLoginRequest,
    OAuthTokenResponse,
    UpdateUserRoleRequest,
    QuickSignupRequest,
    QuickSignupResponse,
)
from ..services.auth_service import AuthService
from ..services.user_service import UserService
from ..services.payment_service import PaymentService
from ..services.oauth_service import OAuthService
from ..database import get_db
from ..config import settings
from ..utils.email_tasks import send_verification_email, send_welcome_email, send_password_reset_email
from ..utils.logging import auth_logger, app_logger
from ..dependencies.rate_limiter import otp_rate_limiter
import httpx

router = APIRouter()

async def create_paystack_customer_and_update_user(
    user_id: int, email: str, first_name: str, last_name: str, phone: str, db: AsyncSession
):
    user_service = UserService(db)
    payment_service = PaymentService(db)
    try:
        customer = await payment_service.create_customer(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
        )
        customer_code = customer["customer_code"]
        await user_service.update_user(
            user_id, UserUpdate(paystack_customer_code=customer_code)
        )
    except httpx.ConnectTimeout:
        app_logger.error(
            "Failed to create Paystack customer due to a connection timeout",
            user_id=user_id
        )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    background_tasks: BackgroundTasks,
    user: RegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        auth_service = AuthService(db)
        user_create = UserCreate(**user.model_dump())
        new_user = await auth_service.register_user(user_create)

        # Create Paystack customer in the background
        background_tasks.add_task(
            create_paystack_customer_and_update_user,
            new_user.id,
            new_user.email,
            new_user.first_name,
            new_user.last_name,
            new_user.phone,
            db,
        )
        
        # Send verification email
        background_tasks.add_task(send_verification_email, new_user)
        background_tasks.add_task(send_welcome_email, new_user)
        
        return new_user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/quick-signup", response_model=QuickSignupResponse, status_code=status.HTTP_201_CREATED)
async def quick_signup(
    background_tasks: BackgroundTasks,
    request: QuickSignupRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Lightweight signup for guest discovery flow.
    
    Allows users to sign up while browsing without full onboarding.
    Location can be provided to set user's initial location.
    Email verification is deferred.
    """
    try:
        auth_service = AuthService(db)
        user_service = UserService(db)
        
        # Create user with minimal data
        user_create = UserCreate(
            email=request.email,
            password=request.password,
            first_name=request.first_name,
            last_name=request.last_name or request.first_name,
            phone=request.phone or "",
            role=request.role,
        )
        
        new_user = await auth_service.register_user(user_create)
        
        # Update location if provided
        if request.latitude is not None and request.longitude is not None:
            await user_service.update_user(
                new_user.id,
                UserUpdate(latitude=request.latitude, longitude=request.longitude)
            )
        
        # Create Paystack customer in the background (non-blocking)
        if request.phone:
            background_tasks.add_task(
                create_paystack_customer_and_update_user,
                new_user.id,
                new_user.email,
                new_user.first_name,
                new_user.last_name,
                request.phone,
                db,
            )
        
        # Send welcome email (defer email verification for quick signup)
        background_tasks.add_task(send_welcome_email, new_user)
        
        # Generate tokens
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth_service.create_access_token(
            data={"sub": str(new_user.id), "role": new_user.role},
            expires_delta=access_token_expires
        )
        
        refresh_token = auth_service.create_refresh_token(
            data={"sub": str(new_user.id), "role": new_user.role}
        )
        
        auth_logger.info(
            "User quick-signed up",
            user_id=new_user.id,
            role=new_user.role
        )
        
        # Extract role value
        role_value = new_user.role.value if hasattr(new_user.role, 'value') else new_user.role
        
        user_data = UserDataResponse(
            id=new_user.id,
            email=new_user.email,
            role=role_value,
            first_name=new_user.first_name,
            is_onboarding_complete=False,
            kyc_status=new_user.kyc_status
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": int(access_token_expires.total_seconds()),
            "user": user_data
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        auth_logger.error(
            "Quick signup failed",
            email=request.email,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create account"
        )


@router.post("/get-role", response_model=GetRoleResponse)
async def get_role(
    request: GetRoleRequest,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    role = await auth_service.get_user_role_by_email(request.email)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return GetRoleResponse(role=role)


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    try:
        user = await auth_service._get_user_by_email(request.email)
        if not user:
            raise ValueError("User not found")
        
        await auth_service.request_password_reset(request.email)
        
        # Send password reset email with OTP in background
        background_tasks.add_task(send_password_reset_email, user)
        
        return {"message": "OTP sent to your email"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@router.post("/verify-otp", response_model=VerifyOTPResponse)
async def verify_otp(
    request: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    result = await auth_service.verify_otp(request.email, request.otp, request.reason.value)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP"
        )

    response_data = {"message": "OTP verified successfully"}
    if request.reason == "password_reset":
        response_data["reset_token"] = result
    elif request.reason == "email_verification":
        response_data["email_verification_token"] = result

    return response_data


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    if not await auth_service.reset_password(request.reset_token, request.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token"
        )
    return {"message": "Password reset successful"}

@router.post("/verify-account")
async def verify_account(
    request: VerifyAccountRequest,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    if not await auth_service.verify_account(request.email, request.email_verification_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token"
        )
    return {"message": "Account verified successfully"}


@router.post("/resend-otp", dependencies=[Depends(otp_rate_limiter)])
async def resend_otp(
    request: ResendOTPRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    try:
        user = await auth_service._get_user_by_email(request.email)
        if not user:
            raise ValueError("User not found")
        
        await auth_service.request_otp(request.email, request.reason.value)
        
        # Send OTP email in background based on reason
        if request.reason.value == "email_verification":
            background_tasks.add_task(send_verification_email, user)
        elif request.reason.value == "password_reset":
            background_tasks.add_task(send_password_reset_email, user)
        
        return {"message": "OTP sent to your email"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    credentials: LoginRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    auth_service = AuthService(db)
    try:
        user = await auth_service.authenticate_user(
            credentials.email, credentials.password, credentials.role
        )
    except ValueError as e:
        # Handle unverified account - return 403 Forbidden with clear message
        if str(e).startswith("UNVERIFIED:"):
            auth_logger.info(
                "Unverified account login attempt - 403 response",
                email=credentials.email
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account not verified. Please check your email for the verification link."
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "role": user.role},
        expires_delta=access_token_expires
    )
    
    refresh_token = auth_service.create_refresh_token(
        data={"sub": str(user.id), "role": user.role}
    )
    
    # Track the active session
    # Extract explicit device headers sent by the frontend
    device_name = request.headers.get("x-device-name", "")
    device_model = request.headers.get("x-device-model", "")
    device_brand = request.headers.get("x-device-brand", "")
    device_type = request.headers.get("x-device-type", "")
    os_name = request.headers.get("x-os-name", "")
    os_version = request.headers.get("x-os-version", "")

    from ..utils.device_utils import get_client_ip
    
    await auth_service.create_user_session(
        user_id=user.id,
        refresh_token=refresh_token,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        device_name=device_name,
        device_model=device_model,
        device_brand=device_brand,
        device_type=device_type,
        os_name=os_name,
        os_version=os_version
    )
    
    auth_logger.info(
        "User logged in successfully",
        user_id=user.id,
        role=user.role
    )
    
    # Include minimal user data in response for immediate frontend use
    # Safely extract role value (could be enum or string)
    role_value = user.role.value if hasattr(user.role, 'value') else user.role
    kyc_status_value = user.kyc_status.value if (user.kyc_status and hasattr(user.kyc_status, 'value')) else user.kyc_status
    
    user_data = UserDataResponse(
        id=user.id,
        email=user.email,
        role=role_value,
        first_name=user.first_name,
        is_onboarding_complete=user.is_onboarding_complete,
        kyc_status=kyc_status_value
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": int(access_token_expires.total_seconds()),
        "user": user_data
    }

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    new_tokens = await auth_service.refresh_tokens(
        refresh_token, 
        ip_address=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", "")
    )
    
    if not new_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_tokens["expires_in"] = int(access_token_expires.total_seconds())
    return new_tokens

@router.post("/logout")
async def logout(
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    await auth_service.logout(refresh_token)
    return {"message": "Successfully logged out"}


@router.post("/oauth/login", response_model=OAuthTokenResponse)
async def oauth_login(
    request: OAuthLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth login endpoint for Google and Apple authentication
    
    Request body:
    - provider: 'google' or 'apple'
    - token: ID token from the provider
    - role: Optional 'worker' or 'employer' (defaults to 'worker')
    - user_id: Optional user ID (used for Apple display name)
    
    Returns access_token, refresh_token, and user information
    """
    try:
        auth_logger.info(f"[/oauth/login] Request received: provider={request.provider}, role={request.role}")
        auth_logger.info(f"[/oauth/login] Token length: {len(request.token) if request.token else 0}")
        
        oauth_service = OAuthService(db)
        tokens = await oauth_service.oauth_login(
            provider=request.provider,
            token=request.token,
            role=request.role,
            user_id=request.user_id,
            first_name=request.first_name,
            last_name=request.last_name
        )
        
        auth_logger.info(
            "OAuth login successful",
            provider=request.provider,
            user_id=tokens.get("user_id")
        )
        
        return OAuthTokenResponse(**tokens)
        
    except HTTPException as e:
        auth_logger.error(f"OAuth login HTTP error: {e.status_code} - {e.detail}", provider=request.provider)
        raise
    except Exception as e:
        auth_logger.error(f"OAuth login error: {str(e)}", error=str(e), provider=request.provider, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth authentication failed"
        )


@router.post("/oauth/verify-google")
async def verify_google_token(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify a Google ID token (for testing/debugging purposes)
    Returns detailed information about the token
    """
    try:
        oauth_service = OAuthService(db)
        
        # Get unverified token info first
        import jwt as pyjwt
        unverified_payload = pyjwt.decode(token, options={"verify_signature": False})
        
        # Then verify
        user_info = await oauth_service.verify_google_token(token)
        
        return {
            "valid": True,
            "user_info": user_info,
            "token_debug": {
                "aud": unverified_payload.get("aud"),
                "email": unverified_payload.get("email"),
                "sub": unverified_payload.get("sub"),
                "iss": unverified_payload.get("iss"),
                "exp": unverified_payload.get("exp"),
            }
        }
    except HTTPException as e:
        auth_logger.error("Google token verification failed", detail=str(e.detail))
        return {
            "valid": False,
            "error": str(e.detail)
        }
    except Exception as e:
        auth_logger.error("Google token verification error", error=str(e))
        return {
            "valid": False,
            "error": str(e)
        }


@router.post("/oauth/verify-apple")
async def verify_apple_token(
    token: str,
    user_id: str = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify an Apple ID token (for testing purposes)
    """
    try:
        oauth_service = OAuthService(db)
        user_info = await oauth_service.verify_apple_token(token, user_id)
        return {"valid": True, "user_info": user_info}
    except HTTPException:
        raise
    except Exception as e:
        auth_logger.error("Apple token verification error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed"
        )


@router.post("/oauth/update-role/{user_id}", response_model=GetRoleResponse)
async def update_oauth_user_role(
    user_id: int,
    request: UpdateUserRoleRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Update user role for first-time OAuth users
    Called after user selects their preferred role
    
    Parameters:
    - user_id: User ID to update
    - role: 'worker' or 'employer'
    """
    try:
        oauth_service = OAuthService(db)
        user = await oauth_service.update_user_role(user_id, request.role)
        
        auth_logger.info(
            "User role updated via OAuth",
            user_id=user.id,
            role=user.role.value
        )
        
        return GetRoleResponse(role=user.role.value)
        
    except HTTPException:
        raise
    except Exception as e:
        auth_logger.error("Error updating user role", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user role"
        )
