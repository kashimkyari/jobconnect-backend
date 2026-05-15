from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from app.models.push_notification_log import PushDeliveryStatus


# ============== Target Filters ==============
class NotificationTargetFilters(BaseModel):
    """Filters for targeting users to receive push notifications"""
    # Legacy/mobile compatibility fields
    user_type: Optional[str] = None  # single role from mobile clients
    is_verified: Optional[bool] = None  # email/account verification
    is_active: Optional[bool] = None  # account status

    user_types: Optional[List[str]] = None  # 'worker', 'employer'
    locations: Optional[List[str]] = None
    subscription_status: Optional[bool] = None  # True for only subscribed users
    require_kyc_verified: bool = False
    exclude_push_disabled: bool = True  # Don't include users who disabled push


# ============== Push Notification Send ==============
class PushNotificationSend(BaseModel):
    """Schema for sending push notifications immediately"""
    title: str
    message: str
    filters: NotificationTargetFilters


class PushNotificationSchedule(BaseModel):
    """Schema for scheduling push notifications for later delivery"""
    title: str
    message: str
    filters: NotificationTargetFilters
    scheduled_time: datetime


# ============== Push Notification Preview ==============
class NotificationPreviewResponse(BaseModel):
    """Response showing how many users match the target filters"""
    total_users: int
    breakdown: dict  # e.g., {'workers': 100, 'employers': 50}
    estimated_delivery_time: str


# ============== Push Delivery Log ==============
class PushNotificationLogResponse(BaseModel):
    """Response for individual push notification delivery log entry"""
    id: int
    admin_id: int
    user_id: int
    title: str
    message: str
    delivery_status: PushDeliveryStatus
    failure_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PushNotificationLogsListResponse(BaseModel):
    """Response for paginated list of push notification logs"""
    total: int
    page: int
    limit: int
    notifications: List[PushNotificationLogResponse]


class PushNotificationBroadcastResponse(BaseModel):
    """Response after sending a broadcast push notification"""
    success: bool
    total_recipients: int
    message: str
    failed_recipients: int = 0


# ============== Push Token Management ==============
class PushTokenUpdate(BaseModel):
    """Schema for updating user's push token"""
    expo_push_token: str
    device_id: Optional[str] = None
    platform: Optional[str] = None
    app_version: Optional[str] = None


class PushTokenResponse(BaseModel):
    """Response after updating push token"""
    success: bool
    message: str


# ============== User Notification Preferences ==============
class NotificationPreferencesUpdate(BaseModel):
    """Schema for updating notification preferences"""
    enable_admin_broadcasts: Optional[bool] = None
    enable_promotional: Optional[bool] = None


class NotificationPreferencesResponse(BaseModel):
    """Response for notification preferences"""
    enable_admin_broadcasts: bool
    enable_promotional: bool
    push_notifications_enabled: bool

    class Config:
        from_attributes = True


# ============== Batch Operations ==============
class PushNotificationBatchResend(BaseModel):
    """Schema for batch resending failed notifications"""
    delivery_status: PushDeliveryStatus = PushDeliveryStatus.FAILED
    limit: int = 100


class BatchResendResponse(BaseModel):
    """Response for batch resend operation"""
    success: bool
    total_resent: int
    message: str
