"""
Admin Push Notification Service
Handles sending, tracking, and managing push notifications from admin panel
"""
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func, or_

from app.models.user import User
from app.models.push_notification_log import PushNotificationLog, PushDeliveryStatus
from app.models.scheduled_push_notification import ScheduledPushNotification, ScheduledPushStatus
from app.models.notification import Notification, NotificationCategory
from app.models.notification_settings import NotificationSettings
from app.models.push_device import PushDevice
from app.models.expo_push_receipt import ExpoPushReceipt
from app.schemas.push_notification import (
    PushNotificationSend,
    NotificationTargetFilters,
    PushNotificationSchedule,
)
from app.utils.expo_client import ExpoClient, get_expo_client

logger = logging.getLogger(__name__)


class AdminPushService:
    """Service for managing admin push notifications"""
    
    def __init__(self, db: AsyncSession, expo_client: Optional[ExpoClient] = None):
        self.db = db
        self.expo_client = expo_client or get_expo_client()
    
    async def get_target_users(
        self,
        filters: NotificationTargetFilters,
    ) -> List[User]:
        """
        Query and return users matching the target filters
        
        Args:
            filters: NotificationTargetFilters containing user segments to target
        
        Returns:
            List of User objects matching the filters
        """
        query = select(User)
        
        # Join with notification settings to check push_notifications preference
        query = query.outerjoin(NotificationSettings)
        
        # Filter by user role/type (support legacy single user_type)
        user_types = filters.user_types or ([filters.user_type] if filters.user_type else None)
        if user_types:
            # Convert to User model roles
            from app.models.user import UserRole
            role_map = {
                'worker': UserRole.WORKER,
                'employer': UserRole.EMPLOYER,
                'admin': UserRole.ADMIN,
            }
            roles = [role_map.get(ut) for ut in user_types if ut in role_map]
            if roles:
                query = query.where(User.role.in_(roles))
        
        # Filter by location
        if filters.locations:
            query = query.where(User.location.in_(filters.locations))
        
        # Filter by subscription status
        if filters.subscription_status is not None:
            query = query.where(User.subscription_status == filters.subscription_status)

        # Filter by user verification (email/account)
        if filters.is_verified is not None:
            query = query.where(User.is_verified == filters.is_verified)
        
        # Filter by KYC verification
        if filters.require_kyc_verified:
            query = query.where(User.is_kyc_verified == True)
        
        # Exclude users with push notifications disabled
        if filters.exclude_push_disabled:
            # Check both User.push_notifications_enabled and NotificationSettings.push_notifications
            query = query.where(
                or_(
                    User.push_notifications_enabled == True,
                    NotificationSettings.push_notifications == True
                )
            )

        active_push_device_exists = (
            select(PushDevice.id)
            .where(
                PushDevice.user_id == User.id,
                PushDevice.provider == "expo",
                PushDevice.is_active == True,
            )
            .exists()
        )
        # Filter by active status if provided; default to active users only.
        active_clause = User.is_active == True
        if filters.is_active is not None:
            active_clause = User.is_active == filters.is_active

        query = query.where(
            and_(
                active_clause,
                or_(
                    and_(
                        User.expo_push_token.isnot(None),
                        User.expo_push_token != "",
                    ),
                    active_push_device_exists,
                ),
            )
        )
        
        # Remove duplicates (in case of multiple settings rows) and order by user ID
        query = query.distinct(User.id).order_by(User.id)
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def _collect_user_tokens(self, users: List[User]) -> Dict[int, List[str]]:
        """
        Build a map of user_id -> active Expo tokens across push_devices + legacy fallback.
        """
        if not users:
            return {}

        user_ids = [user.id for user in users]
        token_map: Dict[int, List[str]] = {user_id: [] for user_id in user_ids}

        device_result = await self.db.execute(
            select(PushDevice).where(
                PushDevice.user_id.in_(user_ids),
                PushDevice.provider == "expo",
                PushDevice.is_active == True,
            )
        )
        devices = device_result.scalars().all()
        for device in devices:
            token = device.expo_push_token
            if token and self.expo_client.validate_token(token):
                if token not in token_map[device.user_id]:
                    token_map[device.user_id].append(token)
            else:
                device.is_active = False
                device.invalidated_reason = "invalid_token_format"

        for user in users:
            legacy_token = user.expo_push_token
            if (
                legacy_token
                and self.expo_client.validate_token(legacy_token)
                and legacy_token not in token_map[user.id]
            ):
                token_map[user.id].append(legacy_token)

        return token_map

    async def _invalidate_token(self, token: str, reason: str = "DeviceNotRegistered") -> None:
        if not token:
            return

        device_result = await self.db.execute(
            select(PushDevice).where(
                PushDevice.expo_push_token == token,
                PushDevice.is_active == True,
            )
        )
        devices = device_result.scalars().all()
        for device in devices:
            device.is_active = False
            device.invalidated_reason = reason

        user_result = await self.db.execute(select(User).where(User.expo_push_token == token))
        users = user_result.scalars().all()
        for user in users:
            user.expo_push_token = None
    
    async def send_push_notification(
        self,
        admin_id: int,
        push_notification: PushNotificationSend,
    ) -> Tuple[Dict, int]:
        """
        Send push notification to targeted users
        
        Args:
            admin_id: ID of the admin sending the notification
            push_notification: Push notification details with filters
        
        Returns:
            Tuple of (result_dict, total_sent)
                - result_dict: {'success': bool, 'total_sent': int, 'failed': int, 'message': str}
                - total_sent: Number of notifications sent
        """
        try:
            # Get targeted users
            target_users = await self.get_target_users(push_notification.filters)
            
            if not target_users:
                return {
                    'success': True,
                    'total_sent': 0,
                    'failed': 0,
                    'message': 'No users matched the target filters',
                }, 0
            
            token_map = await self._collect_user_tokens(target_users)
            tokens = []
            seen = set()
            for user_tokens in token_map.values():
                for token in user_tokens:
                    if token in seen:
                        continue
                    seen.add(token)
                    tokens.append(token)
            
            if not tokens:
                logger.warning(f"Admin {admin_id} tried to send push but no valid tokens found")
                return {
                    'success': False,
                    'total_sent': 0,
                    'failed': len(target_users),
                    'message': 'No users with valid push tokens',
                }, 0
            
            # Send push notifications via Expo
            logger.info(f"Admin {admin_id} sending push to {len(tokens)} users")
            send_results, failed_tokens = await self.expo_client.send_push_notifications(
                tokens=tokens,
                title=push_notification.title,
                body=push_notification.message,
            )
            
            # Log delivery status for each user
            await self._log_delivery_status(
                admin_id=admin_id,
                push_notification=push_notification,
                target_users=target_users,
                token_map=token_map,
                send_results=send_results,
                failed_tokens=failed_tokens,
            )
            
            total_sent = sum(
                1 for result in send_results.values()
                if result.get("status") == "ok"
            )
            
            return {
                'success': True,
                'total_sent': total_sent,
                'failed': len(failed_tokens),
                'message': f'Successfully sent to {total_sent} device tokens',
            }, total_sent
        
        except Exception as e:
            logger.error(f"Error sending push notification: {e}", exc_info=True)
            return {
                'success': False,
                'total_sent': 0,
                'failed': -1,
                'message': f'Error: {str(e)}',
            }, 0

    async def schedule_push_notification(
        self,
        admin_id: int,
        push_notification: PushNotificationSchedule,
    ) -> ScheduledPushNotification:
        scheduled = ScheduledPushNotification(
            admin_id=admin_id,
            title=push_notification.title,
            message=push_notification.message,
            filters=push_notification.filters.model_dump(),
            scheduled_time=push_notification.scheduled_time,
            status=ScheduledPushStatus.SCHEDULED,
        )
        self.db.add(scheduled)
        await self.db.commit()
        await self.db.refresh(scheduled)
        return scheduled

    async def send_scheduled_notification(
        self,
        scheduled: ScheduledPushNotification,
    ) -> ScheduledPushNotification:
        try:
            payload = PushNotificationSend(
                title=scheduled.title,
                message=scheduled.message,
                filters=NotificationTargetFilters(**(scheduled.filters or {})),
            )
            result, _ = await self.send_push_notification(scheduled.admin_id, payload)
            if result.get("success"):
                scheduled.status = ScheduledPushStatus.SENT
                scheduled.sent_at = datetime.now(timezone.utc)
                scheduled.failure_reason = None
            else:
                scheduled.status = ScheduledPushStatus.FAILED
                scheduled.failure_reason = result.get("message", "Unknown error")
        except Exception as exc:
            scheduled.status = ScheduledPushStatus.FAILED
            scheduled.failure_reason = str(exc)
        self.db.add(scheduled)
        await self.db.commit()
        await self.db.refresh(scheduled)
        return scheduled

    async def process_due_scheduled_notifications(self) -> int:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(ScheduledPushNotification)
            .where(
                ScheduledPushNotification.status == ScheduledPushStatus.SCHEDULED,
                ScheduledPushNotification.scheduled_time <= now,
            )
            .order_by(ScheduledPushNotification.scheduled_time.asc())
        )
        scheduled_items = result.scalars().all()
        sent = 0
        for item in scheduled_items:
            await self.send_scheduled_notification(item)
            if item.status == ScheduledPushStatus.SENT:
                sent += 1
        return sent
    
    async def _log_delivery_status(
        self,
        admin_id: int,
        push_notification: PushNotificationSend,
        target_users: List[User],
        token_map: Dict[int, List[str]],
        send_results: Dict,
        failed_tokens: List[str],
    ) -> None:
        """
        Log delivery status for all sent push notifications
        
        Args:
            admin_id: ID of admin sending notification
            push_notification: Push notification details
            target_users: List of target users
            send_results: Results from Expo API
            failed_tokens: Tokens that failed to send
        """
        logs_to_create: List[PushNotificationLog] = []
        user_log_map: Dict[int, PushNotificationLog] = {}
        failed_token_set = set(failed_tokens or [])
        
        for user in target_users:
            user_tokens = token_map.get(user.id, [])
            if not user_tokens:
                # User doesn't have a token
                log = PushNotificationLog(
                    admin_id=admin_id,
                    user_id=user.id,
                    title=push_notification.title,
                    message=push_notification.message,
                    delivery_status=PushDeliveryStatus.NOT_SENT,
                    failure_reason="User has push notifications disabled or no token available",
                )
                logger.info(f"LOG: User {user.id} has no token - status NOT_SENT")
            else:
                token_results = [send_results.get(token, {}) for token in user_tokens]
                succeeded = any(r.get("status") == "ok" for r in token_results)
                if succeeded:
                    log = PushNotificationLog(
                        admin_id=admin_id,
                        user_id=user.id,
                        title=push_notification.title,
                        message=push_notification.message,
                        delivery_status=PushDeliveryStatus.SENT,
                    )
                    logger.info(f"LOG: User {user.id} notification sent - status SENT")
                else:
                    first_failed = next(
                        (send_results.get(token, {}) for token in user_tokens if token in failed_token_set),
                        {},
                    )
                    failure_reason = first_failed.get("error", "Unknown error")
                    log = PushNotificationLog(
                        admin_id=admin_id,
                        user_id=user.id,
                        title=push_notification.title,
                        message=push_notification.message,
                        delivery_status=PushDeliveryStatus.FAILED,
                        failure_reason=failure_reason,
                    )
                    logger.info(f"LOG: User {user.id} token failed - status FAILED")
                    for token in user_tokens:
                        result = send_results.get(token, {})
                        if result.get("error_code") == "DeviceNotRegistered":
                            await self._invalidate_token(token, reason="DeviceNotRegistered")
            
            logs_to_create.append(log)
            user_log_map[user.id] = log
        
        # Batch insert logs
        self.db.add_all(logs_to_create)
        await self.db.flush()

        # Create in-app notifications so offline users see admin broadcasts on next launch.
        inbox_rows: List[Notification] = []
        for user in target_users:
            inbox_rows.append(
                Notification(
                    user_id=user.id,
                    title=push_notification.title,
                    message=push_notification.message,
                    category=NotificationCategory.PLATFORM_UPDATES.value,
                )
            )
        if inbox_rows:
            self.db.add_all(inbox_rows)

        # Track successful Expo tickets for later receipt polling.
        ticket_rows: List[ExpoPushReceipt] = []
        ticket_map = {
            token: result.get("id")
            for token, result in send_results.items()
            if result.get("status") == "ok" and result.get("id")
        }
        if ticket_map:
            ticket_ids = list(ticket_map.values())
            existing_result = await self.db.execute(
                select(ExpoPushReceipt.ticket_id).where(ExpoPushReceipt.ticket_id.in_(ticket_ids))
            )
            existing_ticket_ids = {row[0] for row in existing_result.all()}

            device_result = await self.db.execute(
                select(PushDevice.id, PushDevice.expo_push_token).where(
                    PushDevice.expo_push_token.in_(list(ticket_map.keys()))
                )
            )
            device_map = {token: device_id for device_id, token in device_result.all()}

            for user in target_users:
                log = user_log_map.get(user.id)
                if not log:
                    continue
                for token in token_map.get(user.id, []):
                    ticket_id = ticket_map.get(token)
                    if not ticket_id or ticket_id in existing_ticket_ids:
                        continue
                    ticket_rows.append(
                        ExpoPushReceipt(
                            ticket_id=ticket_id,
                            source_type="admin_broadcast",
                            status="sent",
                            expo_push_token=token,
                            user_id=user.id,
                            push_device_id=device_map.get(token),
                            admin_log_id=log.id,
                        )
                    )
                    existing_ticket_ids.add(ticket_id)

        if ticket_rows:
            self.db.add_all(ticket_rows)
        
        try:
            await self.db.commit()
            logger.info(f"[DB] Successfully committed {len(logs_to_create)} delivery status logs for admin {admin_id}")
        except Exception as e:
            logger.error(f"[DB] Error committing delivery status logs: {e}", exc_info=True)
            await self.db.rollback()
            raise
    
    async def get_delivery_logs(
        self,
        admin_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 50,
        delivery_status: Optional[PushDeliveryStatus] = None,
    ) -> Tuple[List[PushNotificationLog], int]:
        """
        Get paginated delivery logs
        
        Args:
            admin_id: Filter by admin ID (optional)
            skip: Pagination offset
            limit: Pagination limit
            delivery_status: Filter by delivery status (optional)
        
        Returns:
            Tuple of (logs, total_count)
        """
        query = select(PushNotificationLog)
        count_query = select(func.count(PushNotificationLog.id))
        
        if admin_id:
            query = query.where(PushNotificationLog.admin_id == admin_id)
            count_query = count_query.where(PushNotificationLog.admin_id == admin_id)
        
        if delivery_status:
            query = query.where(PushNotificationLog.delivery_status == delivery_status)
            count_query = count_query.where(PushNotificationLog.delivery_status == delivery_status)
        
        # Get total count
        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()
        
        # Get paginated results
        query = query.order_by(PushNotificationLog.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        logs = result.scalars().all()
        
        return logs, total
    
    async def get_target_user_count(
        self,
        filters: NotificationTargetFilters,
    ) -> Dict[str, int]:
        """
        Get count of users matching target filters, broken down by role
        
        Args:
            filters: NotificationTargetFilters
        
        Returns:
            Dict with breakdown by role and total
        """
        target_users = await self.get_target_users(filters)
        
        from app.models.user import UserRole
        
        breakdown = {
            'workers': 0,
            'employers': 0,
            'admins': 0,
            'total': len(target_users),
        }
        
        for user in target_users:
            if user.role == UserRole.WORKER:
                breakdown['workers'] += 1
            elif user.role == UserRole.EMPLOYER:
                breakdown['employers'] += 1
            elif user.role == UserRole.ADMIN:
                breakdown['admins'] += 1
        
        return breakdown
    
    async def update_push_token(
        self,
        user_id: int,
        expo_push_token: str,
        device_id: Optional[str] = None,
        platform: Optional[str] = None,
        app_version: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Update a user's push token
        
        Args:
            user_id: ID of the user
            expo_push_token: New Expo push token
            device_id: Stable per-installation ID (optional)
            platform: Device platform e.g., ios/android (optional)
            app_version: App version string (optional)
        
        Returns:
            Tuple[success, reason]
        """
        try:
            user = await self.db.get(User, user_id)
            if not user:
                logger.warning(f"User {user_id} not found for token update")
                return False, "user_not_found"

            token = expo_push_token.strip() if isinstance(expo_push_token, str) else ""
            if not token:
                logger.warning("Empty Expo token for user %s", user_id)
                return False, "missing_token"
            
            # Validate token format
            if not self.expo_client.validate_token(token):
                logger.warning(
                    "Invalid Expo token format for user %s (prefix=%s)",
                    user_id,
                    token[:20],
                )
                return False, "invalid_token_format"

            # Keep legacy single-token field for backward compatibility.
            user.expo_push_token = token

            # Prefer existing row by exact token to preserve history.
            existing_token_result = await self.db.execute(
                select(PushDevice).where(PushDevice.expo_push_token == token)
            )
            push_device = existing_token_result.scalar_one_or_none()

            # Otherwise, upsert by (user_id, device_id) when provided.
            if not push_device and device_id:
                existing_device_result = await self.db.execute(
                    select(PushDevice).where(
                        PushDevice.user_id == user_id,
                        PushDevice.device_id == device_id,
                        PushDevice.provider == "expo",
                    ).order_by(PushDevice.updated_at.desc()).limit(1)
                )
                push_device = existing_device_result.scalars().first()

            if not push_device:
                push_device = PushDevice(
                    user_id=user_id,
                    expo_push_token=token,
                    provider="expo",
                )
                self.db.add(push_device)
                await self.db.flush()

            push_device.user_id = user_id
            push_device.expo_push_token = token
            push_device.provider = "expo"
            push_device.platform = platform
            push_device.device_id = device_id
            push_device.app_version = app_version
            push_device.is_active = True
            push_device.invalidated_reason = None
            push_device.last_seen_at = datetime.now(timezone.utc)

            # If this device rotated tokens, mark older records for same device inactive.
            if device_id:
                duplicates_result = await self.db.execute(
                    select(PushDevice).where(
                        PushDevice.user_id == user_id,
                        PushDevice.device_id == device_id,
                        PushDevice.provider == "expo",
                        PushDevice.id != push_device.id,
                        PushDevice.is_active == True,
                    )
                )
                duplicates = duplicates_result.scalars().all()
                for dup in duplicates:
                    dup.is_active = False
                    dup.invalidated_reason = "token_rotated"

            await self.db.commit()
            logger.info(f"Updated push token for user {user_id}: {token[:20]}...")
            return True, "ok"
        
        except Exception as e:
            logger.error(f"Error updating push token for user {user_id}: {e}")
            import traceback
            traceback.print_exc()
            return False, "internal_error"
    
    async def resend_specific_notification(
        self,
        log_id: int,
    ) -> Dict:
        """
        Resend a specific failed notification
        
        Args:
            log_id: ID of the PushNotificationLog to resend
        
        Returns:
            Dict with resend result
        """
        try:
            # Get the specific log
            log = await self.db.get(PushNotificationLog, log_id)
            if not log:
                return {
                    'success': False,
                    'message': 'Notification log not found',
                    'resent': 0,
                }
            
            # Get the user for this log
            user = await self.db.get(User, log.user_id)
            if not user:
                log.failure_reason = "User no longer has valid push token"
                await self.db.commit()
                return {
                    'success': False,
                    'message': 'User no longer has valid push token',
                    'resent': 0,
                }

            token_map = await self._collect_user_tokens([user])
            tokens = token_map.get(user.id, [])
            if not tokens:
                log.failure_reason = "User no longer has valid push token"
                await self.db.commit()
                return {
                    'success': False,
                    'message': 'User no longer has valid push token',
                    'resent': 0,
                }
            
            # Send the notification again
            send_results, failed_tokens = await self.expo_client.send_push_notifications(
                tokens=tokens,
                title=log.title,
                body=log.message,
            )
            for failed_token in failed_tokens:
                if send_results.get(failed_token, {}).get("error_code") == "DeviceNotRegistered":
                    await self._invalidate_token(failed_token, reason="DeviceNotRegistered")
            
            successful_tokens = [
                token for token in tokens
                if send_results.get(token, {}).get("status") == "ok"
            ]
            if not successful_tokens:
                first_failed_token = next((token for token in tokens if token in failed_tokens), None)
                log.failure_reason = send_results.get(first_failed_token, {}).get('error', 'Unknown error')
                await self.db.commit()
                return {
                    'success': False,
                    'message': f"Failed to resend: {log.failure_reason}",
                    'resent': 0,
                }
            
            # Update status to sent
            log.delivery_status = PushDeliveryStatus.SENT
            log.failure_reason = None
            await self.db.commit()
            
            logger.info(f"Resent notification {log_id} to user {user.id}")
            return {
                'success': True,
                'message': 'Notification resent successfully',
                'resent': 1,
            }
        
        except Exception as e:
            logger.error(f"Error resending notification {log_id}: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'Error: {str(e)}',
                'resent': 0,
            }
    
    async def resend_failed_notifications(
        self,
        limit: int = 100,
    ) -> Dict:
        """
        Resend notifications that failed
        
        Args:
            limit: Maximum number of failed notifications to resend
        
        Returns:
            Dict with resend statistics
        """
        # Get failed deliveries from last 24 hours
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        
        query = select(PushNotificationLog).where(
            and_(
                PushNotificationLog.delivery_status == PushDeliveryStatus.FAILED,
                PushNotificationLog.created_at >= cutoff_time,
            )
        ).limit(limit)
        
        result = await self.db.execute(query)
        failed_logs = result.scalars().all()
        
        if not failed_logs:
            return {'success': True, 'resent': 0, 'message': 'No failed notifications to resend'}
        
        # Group by title and message to resend together
        grouped = {}
        for log in failed_logs:
            key = (log.title, log.message)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(log)
        
        total_resent = 0
        
        for (title, message), logs in grouped.items():
            users = [log.user for log in logs]
            token_map = await self._collect_user_tokens(users)
            tokens = []
            seen = set()
            for user_tokens in token_map.values():
                for token in user_tokens:
                    if token in seen:
                        continue
                    seen.add(token)
                    tokens.append(token)
            
            if tokens:
                send_results, failed_tokens = await self.expo_client.send_push_notifications(
                    tokens=tokens,
                    title=title,
                    body=message,
                )
                for failed_token in failed_tokens:
                    if send_results.get(failed_token, {}).get("error_code") == "DeviceNotRegistered":
                        await self._invalidate_token(failed_token, reason="DeviceNotRegistered")
                
                total_resent += len(send_results) - len(failed_tokens)
                
                # Update delivery status
                for log in logs:
                    user_tokens = token_map.get(log.user_id, [])
                    if any(send_results.get(token, {}).get("status") == "ok" for token in user_tokens):
                        log.delivery_status = PushDeliveryStatus.SENT
                        log.failure_reason = None
                    else:
                        log.failure_reason = "Retry failed"
        
        await self.db.commit()
        return {
            'success': True,
            'resent': total_resent,
            'message': f'Resent {total_resent} notifications',
        }
    async def send_test_notification(self, push_token: str, admin_id: int = None) -> Dict:
        """
        Send a test notification to verify the push notification system is working
        
        Args:
            push_token: The Expo push token to send the test notification to
            admin_id: Optional admin ID for logging purposes
            
        Returns:
            Dictionary with success status and message
        """
        try:
            if not push_token:
                return {
                    'success': False,
                    'message': 'No valid push token provided'
                }
            
            # Send test notification
            send_results, failed_tokens = await self.expo_client.send_push_notifications(
                tokens=[push_token],
                title="Test Notification",
                body="This is a test push notification from JobConnect Admin. If you see this, push notifications are working!",
                data={
                    'type': 'test',
                    'timestamp': datetime.utcnow().isoformat(),
                }
            )
            
            # Log the test notification if admin_id is provided
            if admin_id:
                success = push_token not in failed_tokens
                log = PushNotificationLog(
                    admin_id=admin_id,
                    user_id=admin_id,  # Log against admin user for NOT NULL constraint
                    title="Test Notification",
                    message="This is a test push notification from JobConnect Admin. If you see this, push notifications are working!",
                    delivery_status=PushDeliveryStatus.SENT if success else PushDeliveryStatus.FAILED,
                    failure_reason=None if success else "Test notification failed to deliver",
                )
                self.db.add(log)
                try:
                    await self.db.commit()
                    logger.info(f"[DB] Test notification logged for admin {admin_id}")
                except Exception as e:
                    logger.error(f"[DB] Error logging test notification: {e}", exc_info=True)
                    await self.db.rollback()
            
            if push_token in failed_tokens:
                return {
                    'success': False,
                    'message': 'Failed to send test notification - token may be invalid'
                }
            
            logger.info(f"Test notification sent successfully to token: {push_token[:20]}...")
            return {
                'success': True,
                'message': 'Test notification sent successfully'
            }
        
        except Exception as e:
            logger.error(f"Error sending test notification: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'Error sending test notification: {str(e)}'
            }
