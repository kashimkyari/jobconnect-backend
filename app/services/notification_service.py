from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, func
from app.models.user import User
from app.models.notification_settings import NotificationSettings
from app.models.notification import Notification
from app.models.push_device import PushDevice
from app.models.expo_push_receipt import ExpoPushReceipt
from app.schemas.notification import NotificationCreate
from typing import Dict, List, Optional
from app.websocket_manager import manager
from app.utils.expo_client import get_expo_client
import logging
import asyncio

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.expo_client = get_expo_client()

    @staticmethod
    def _as_role_value(user: User) -> Optional[str]:
        role = getattr(user, "role", None)
        if role is None:
            return None
        return getattr(role, "value", str(role))

    def _build_client_payload(self, notification: Notification, user: Optional[User]) -> Dict:
        action_payload = notification.action_payload or {}
        if not isinstance(action_payload, dict):
            action_payload = {}

        related_id = action_payload.get("related_id")
        job_id = action_payload.get("job_id")
        booking_id = action_payload.get("booking_id")
        application_id = action_payload.get("application_id")
        conversation_id = action_payload.get("conversation_id") or action_payload.get("chat_id")

        return {
            "notification_id": notification.id,
            "title": notification.title,
            "body": notification.message,
            "message": notification.message,
            "subtitle": "JobConnect",
            "category": notification.category,
            "type": "notification",
            "notification_type": notification.category,
            "created_at": notification.created_at.isoformat() if notification.created_at else None,
            "timestamp": notification.created_at.isoformat() if notification.created_at else None,
            "recipient_role": self._as_role_value(user) if user else None,
            "action_screen": notification.action_screen,
            "action_payload": action_payload,
            "screen": notification.action_screen,
            "related_id": related_id,
            "job_id": job_id,
            "booking_id": booking_id,
            "application_id": application_id,
            "conversation_id": conversation_id,
            "deep_link": action_payload.get("deep_link") or action_payload.get("deepLink"),
            "image_url": action_payload.get("image_url") or action_payload.get("imageUrl"),
        }

    async def _send_realtime_notification(self, user_id: int, payload: Dict) -> None:
        await manager.send_personal_json(
            data={"type": "new_notification", "data": payload},
            user_id=user_id,
        )

    async def _push_enabled(self, user: User) -> bool:
        if user.push_notifications_enabled is False:
            return False

        settings_result = await self.db.execute(
            select(NotificationSettings).where(NotificationSettings.user_id == user.id)
        )
        settings = settings_result.scalar_one_or_none()
        if settings and settings.push_notifications is False:
            return False

        return True

    @staticmethod
    def _is_application_update(payload: Dict) -> bool:
        action_screen = str(payload.get("action_screen") or "")
        application_id = payload.get("application_id")
        if application_id is not None:
            return True
        application_screens = {"ApplicantsList", "JobApplicants", "ApplicationDetails"}
        return action_screen in application_screens

    def _is_category_enabled(self, settings: Optional[NotificationSettings], payload: Dict) -> bool:
        if settings is None:
            return True

        category = str(payload.get("category") or "").lower()
        if category == "messages":
            return bool(getattr(settings, "new_message", True))

        if category == "jobs_and_matches":
            if self._is_application_update(payload):
                return bool(getattr(settings, "application_updates", True))
            return bool(getattr(settings, "job_updates", True))

        # For categories that don't yet have explicit DB toggles, keep enabled.
        return True

    async def _get_active_push_tokens(self, user: User) -> List[str]:
        if not await self._push_enabled(user):
            return []

        tokens: List[str] = []
        changed = False

        devices_result = await self.db.execute(
            select(PushDevice).where(
                PushDevice.user_id == user.id,
                PushDevice.provider == "expo",
                PushDevice.is_active == True,
            )
        )
        devices = devices_result.scalars().all()
        for device in devices:
            token = device.expo_push_token
            if not token or not self.expo_client.validate_token(token):
                device.is_active = False
                device.invalidated_reason = "invalid_token_format"
                changed = True
                continue
            if token not in tokens:
                tokens.append(token)

        # Backward-compatibility fallback to legacy users.expo_push_token.
        legacy_token = user.expo_push_token
        if legacy_token:
            if self.expo_client.validate_token(legacy_token):
                if legacy_token not in tokens:
                    tokens.append(legacy_token)
            else:
                logger.warning("Invalid legacy Expo token format for user %s", user.id)
                user.expo_push_token = None
                changed = True

        if changed:
            await self.db.commit()

        return tokens

    async def _mark_token_invalid(self, user: User, token: str, reason: str = "DeviceNotRegistered") -> None:
        if not token:
            return

        devices_result = await self.db.execute(
            select(PushDevice).where(PushDevice.expo_push_token == token, PushDevice.is_active == True)
        )
        devices = devices_result.scalars().all()
        for device in devices:
            device.is_active = False
            device.invalidated_reason = reason

        if user.expo_push_token == token:
            user.expo_push_token = None

    async def _record_push_tickets(
        self,
        *,
        user_id: int,
        notification_id: Optional[int],
        send_results: Dict[str, Dict],
    ) -> None:
        ticket_map = {
            token: result.get("id")
            for token, result in send_results.items()
            if result.get("status") == "ok" and result.get("id")
        }
        if not ticket_map:
            return

        ticket_ids = list(ticket_map.values())
        existing_result = await self.db.execute(
            select(ExpoPushReceipt.ticket_id).where(ExpoPushReceipt.ticket_id.in_(ticket_ids))
        )
        existing_ticket_ids = {row[0] for row in existing_result.all()}

        device_map: Dict[str, int] = {}
        token_list = list(ticket_map.keys())
        device_result = await self.db.execute(
            select(PushDevice.id, PushDevice.expo_push_token).where(
                PushDevice.expo_push_token.in_(token_list)
            )
        )
        for device_id, token in device_result.all():
            device_map[token] = device_id

        rows: List[ExpoPushReceipt] = []
        for token, ticket_id in ticket_map.items():
            if ticket_id in existing_ticket_ids:
                continue
            rows.append(
                ExpoPushReceipt(
                    ticket_id=ticket_id,
                    source_type="transactional",
                    status="sent",
                    expo_push_token=token,
                    user_id=user_id,
                    push_device_id=device_map.get(token),
                    notification_id=notification_id,
                )
            )

        if rows:
            self.db.add_all(rows)

    async def _send_push_notification(self, user: User, payload: Dict, notification_id: Optional[int]) -> None:
        tokens = await self._get_active_push_tokens(user)
        if not tokens:
            return

        image_url = payload.get("image") or payload.get("image_url")
        send_results, failed_tokens = await self.expo_client.send_push_notifications(
            tokens=tokens,
            title=payload["title"],
            body=payload["body"],
            data=payload,
            image=image_url,
        )

        if failed_tokens:
            for failed_token in failed_tokens:
                token_result = send_results.get(failed_token, {})
                error_code = token_result.get("error_code")
                logger.warning(
                    "Push notification failed for user %s (token suffix %s): %s",
                    user.id,
                    failed_token[-8:] if len(failed_token) >= 8 else failed_token,
                    token_result.get("error", "Unknown error"),
                )
                if error_code == "DeviceNotRegistered":
                    await self._mark_token_invalid(user, failed_token, reason=error_code)

        await self._record_push_tickets(
            user_id=user.id,
            notification_id=notification_id,
            send_results=send_results,
        )
        await self.db.commit()

    async def send_push_only(self, user_id: int, payload: Dict) -> bool:
        """
        Send a push notification without creating a Notification DB row.
        Respects notification settings and push enablement.
        """
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return False

        settings_result = await self.db.execute(
            select(NotificationSettings).where(NotificationSettings.user_id == user.id)
        )
        settings = settings_result.scalar_one_or_none()

        if not self._is_category_enabled(settings, payload):
            logger.info(
                "Push-only notification suppressed by user settings: user_id=%s category=%s",
                user.id,
                payload.get("category"),
            )
            return False

        try:
            await self._send_push_notification(user=user, payload=payload, notification_id=None)
            return True
        except Exception as e:
            logger.error(
                "Failed to send push-only notification to user %s: %s",
                user.id,
                e,
            )
            return False

    async def create_notification(self, notification_in: NotificationCreate) -> Notification:
        """
        Creates and saves a new notification, then triggers:
        1) real-time websocket notification
        2) Expo push notification (when enabled for user)
        """
        category_value = (
            notification_in.category.value
            if hasattr(notification_in.category, "value")
            else str(notification_in.category)
        )

        notification = Notification(
            user_id=notification_in.user_id,
            title=notification_in.title,
            message=notification_in.message,
            category=category_value,
            action_screen=notification_in.action_screen,
            action_payload=notification_in.action_payload,
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)

        user_result = await self.db.execute(
            select(User).where(User.id == notification.user_id)
        )
        user = user_result.scalar_one_or_none()
        payload = self._build_client_payload(notification=notification, user=user)
        settings = None
        if user:
            settings_result = await self.db.execute(
                select(NotificationSettings).where(NotificationSettings.user_id == user.id)
            )
            settings = settings_result.scalar_one_or_none()

        delivery_enabled = self._is_category_enabled(settings, payload)

        # Trigger real-time notification via WebSocket.
        if delivery_enabled:
            try:
                await self._send_realtime_notification(user_id=notification.user_id, payload=payload)
            except Exception as e:
                logger.error(
                    "Failed to send real-time notification to user %s: %s",
                    notification.user_id,
                    e,
                )
        else:
            logger.info(
                "Realtime notification suppressed by user settings: user_id=%s category=%s",
                notification.user_id,
                payload.get("category"),
            )

        # Trigger push notification via Expo.
        if user and delivery_enabled:
            try:
                await self._send_push_notification(
                    user=user,
                    payload=payload,
                    notification_id=notification.id,
                )
            except Exception as e:
                logger.error(
                    "Failed to send push notification to user %s: %s",
                    notification.user_id,
                    e,
                )
        elif user:
            logger.info(
                "Push notification suppressed by user settings: user_id=%s category=%s",
                notification.user_id,
                payload.get("category"),
            )

        return notification

    async def get_user_notifications(self, user_id: int, skip: int = 0, limit: int = 20) -> List[Notification]:
        """
        Retrieves all notifications for a specific user, with pagination.
        """
        query = (
            select(Notification)
            .filter(Notification.user_id == user_id, Notification.category != "messages")
            .order_by(Notification.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_unread_notification_count(self, user_id: int) -> int:
        """
        Gets the count of unread notifications for a user.
        """
        query = select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.read == False,
            Notification.category != "messages",
        )
        result = await self.db.execute(query)
        return result.scalar_one()

    async def get_notification_by_id(self, notification_id: int) -> Optional[Notification]:
        """
        Retrieves a single notification by its ID.
        """
        return await self.db.get(Notification, notification_id)

    async def mark_notification_as_read(self, notification_id: int, user_id: int) -> Optional[Notification]:
        """
        Marks a single notification as read for a given user.
        """
        notification = await self.get_notification_by_id(notification_id)
        if notification and notification.user_id == user_id:
            notification.read = True
            await self.db.commit()
            await self.db.refresh(notification)
            return notification
        return None

    async def mark_all_notifications_as_read(self, user_id: int) -> int:
        """
        Marks all unread notifications as read for a user and returns the count of updated notifications.
        """
        stmt = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read == False)
            .values(read=True)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def send_welcome_email(self, user_email: str, first_name: str):
        """
        Sends a welcome email to a new user.
        """
        # This is a placeholder for the actual email sending logic.
        # In a real application, you would use a service like SendGrid or Amazon SES.
        print(f"Sending welcome email to {user_email}...")
        # Simulate sending email
        await asyncio.sleep(1)
        print(f"Welcome email sent to {user_email}.")
