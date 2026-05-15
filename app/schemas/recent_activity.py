from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any

class RecentActivityBase(BaseModel):
    activity_type: str
    description: str
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None
    activity_data: Optional[Dict[str, Any]] = None

class RecentActivityCreate(RecentActivityBase):
    user_id: int

class RecentActivityOut(RecentActivityBase):
    id: int
    user_id: int
    timestamp: datetime

    class Config:
        from_attributes = True
