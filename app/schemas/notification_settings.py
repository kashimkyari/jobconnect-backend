from pydantic import BaseModel

class NotificationSettingsBase(BaseModel):
    push_notifications: bool
    email_notifications: bool
    job_updates: bool
    application_updates: bool
    new_message: bool

class NotificationSettingsCreate(NotificationSettingsBase):
    pass

class NotificationSettingsUpdate(NotificationSettingsBase):
    pass

class NotificationSettings(NotificationSettingsBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True
