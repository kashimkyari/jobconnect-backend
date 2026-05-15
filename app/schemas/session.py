from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class SessionBase(BaseModel):
    id: str
    device_name: Optional[str] = None
    device_model: Optional[str] = None
    device_brand: Optional[str] = None
    device_type: Optional[str] = None
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    ip_address: Optional[str] = None
    location: Optional[str] = None
    is_active: bool
    is_current: bool = False
    last_used_at: datetime
    created_at: datetime

class SessionResponse(SessionBase):
    class Config:
        from_attributes = True

class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]
