from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.auth_service import get_current_user
from app.models.user import User
from app.schemas.notification_settings import NotificationSettings, NotificationSettingsUpdate
from app.services import notification_settings_service

router = APIRouter()

@router.get("/settings/notifications", response_model=NotificationSettings)
async def get_user_notification_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    settings = await notification_settings_service.get_notification_settings(db, current_user.id)
    if not settings:
        settings = await notification_settings_service.create_notification_settings(db, current_user)
    return settings

@router.put("/settings/notifications", response_model=NotificationSettings)
async def update_user_notification_settings(
    settings: NotificationSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    updated_settings = await notification_settings_service.update_notification_settings(db, current_user.id, settings)
    if not updated_settings:
        raise HTTPException(status_code=404, detail="Settings not found")
    return updated_settings
