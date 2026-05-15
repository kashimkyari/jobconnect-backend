from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class OTPReason(str, Enum):
    password_reset = "password_reset"
    email_verification = "email_verification"


# Request Schemas
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    first_name: str = Field(..., min_length=2)
    last_name: str = Field(..., min_length=2)
    phone: str = Field(..., pattern=r'^\+?1?\d{9,15}$')
    role: str = Field(..., pattern='^(worker|employer|admin)$')
    referral_code: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    role: Optional[str] = None

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str = Field(..., min_length=8)


class VerifyOTPRequest(BaseModel):
    otp: str
    email: EmailStr
    reason: OTPReason


class VerifyOTPResponse(BaseModel):
    reset_token: Optional[str] = None
    email_verification_token: Optional[str] = None
    message: str


class VerifyAccountRequest(BaseModel):
    email: EmailStr
    email_verification_token: str

class ResendOTPRequest(BaseModel):
    email: EmailStr
    reason: OTPReason


class GetRoleRequest(BaseModel):
    email: EmailStr


# OAuth Schemas
class OAuthLoginRequest(BaseModel):
    provider: str = Field(..., pattern='^(google|apple)$')
    token: str
    role: Optional[str] = Field(None, pattern='^(worker|employer)$')
    user_id: Optional[str] = None  # Used for Apple (display name)
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class OAuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user_id: int
    email: str
    role: Optional[str] = None  # None for new OAuth users before role selection
    first_name: str
    is_new_user: bool = False
    kyc_status: str = "not_started"
    is_onboarding_complete: bool = False
    avatar_url: Optional[str] = None


class UpdateUserRoleRequest(BaseModel):
    role: str = Field(..., pattern='^(worker|employer)$')


# Response Schemas
class GetRoleResponse(BaseModel):
    role: str


class UserDataResponse(BaseModel):
    """Minimal user data returned with login response"""
    id: int
    email: str
    role: str
    first_name: Optional[str] = None
    is_onboarding_complete: Optional[bool] = None
    kyc_status: Optional[str] = None

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Response for login endpoint with user data and tokens"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    user: Optional[UserDataResponse] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class RoleSwitchResponse(BaseModel):
    """Response for role switch containing new tokens and updated user"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: 'AuthUserResponse'

    class Config:
        from_attributes = True


class AuthUserResponse(BaseModel):
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    role: str
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuickSignupRequest(BaseModel):
    """Lightweight signup for guest discovery flow"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    first_name: str = Field(..., min_length=2)
    last_name: Optional[str] = None
    phone: Optional[str] = None
    role: str = Field(..., pattern='^(worker|employer)$')
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class QuickSignupResponse(BaseModel):
    """Response from quick signup endpoint"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserDataResponse
