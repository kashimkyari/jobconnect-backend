from sqlalchemy.orm import Session
from sqlalchemy.future import select
from app.models.notification_settings import NotificationSettings
from app.schemas.notification_settings import NotificationSettingsCreate, NotificationSettingsUpdate
from app.models.user import User

async def get_notification_settings(db: Session, user_id: int):
    result = await db.execute(select(NotificationSettings).filter(NotificationSettings.user_id == user_id))
    return result.scalars().first()

async def create_notification_settings(db: Session, user: User):
    db_settings = NotificationSettings(user_id=user.id)
    db.add(db_settings)
    await db.commit()
    await db.refresh(db_settings)
    return db_settings

async def update_notification_settings(db: Session, user_id: int, settings: NotificationSettingsUpdate):
    db_settings = await get_notification_settings(db, user_id)
    if not db_settings:
        return None
    
    for var, value in vars(settings).items():
        setattr(db_settings, var, value) if value is not None else None

    db.add(db_settings)
    await db.commit()
    await db.refresh(db_settings)
    return db_settings
