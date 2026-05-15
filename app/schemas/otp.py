from pydantic import BaseModel
import uuid
from datetime import datetime

class OTPBase(BaseModel):
    otp_code: str
    user_id: int
    purpose: str
    expires_at: datetime

class OTPCreate(OTPBase):
    pass

class OTP(OTPBase):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True
