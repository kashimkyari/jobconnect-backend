from pydantic import AliasChoices, BaseModel, Field, model_validator
from datetime import datetime
from typing import Optional, Dict, Any
from app.models.notification import NotificationCategory

class NotificationBase(BaseModel):
    title: str
    message: str
    # Accept both `category` and legacy `notification_category` from callers.
    category: NotificationCategory = Field(
        validation_alias=AliasChoices("category", "notification_category")
    )
    action_screen: Optional[str] = None
    action_payload: Optional[Dict[str, Any]] = None
    # Backward-compatible bridge for legacy callers that only pass `related_id`.
    related_id: Optional[int] = None

    @model_validator(mode="after")
    def attach_related_id_to_payload(self):
        if self.related_id is None:
            return self

        payload = dict(self.action_payload or {})
        payload.setdefault("related_id", self.related_id)
        self.action_payload = payload
        return self

class NotificationCreate(NotificationBase):
    user_id: int

class NotificationUpdate(BaseModel):
    read: Optional[bool] = None

class NotificationResponse(NotificationBase):
    id: int
    user_id: int
    read: bool
    created_at: datetime

    class Config:
        from_attributes = True
