from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from pydantic.alias_generators import to_camel


class WaitlistBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    user_type: str
    location: str
    newsletter: Optional[bool] = False

    class Config:
        from_attributes = True
        alias_generator = to_camel
        validate_by_name = True
        

class WaitlistCreate(WaitlistBase):
    pass

class Waitlist(WaitlistBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
        alias_generator = to_camel
        validate_by_name = True
