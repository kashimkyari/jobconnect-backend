from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expo_push_receipt import ExpoPushReceipt
from app.models.push_device import PushDevice
from app.models.push_notification_log import PushDeliveryStatus
from app.models.user import User
from app.utils.expo_client import ExpoClient, get_expo_client


class PushReceiptService:
    def __init__(self, db: AsyncSession, expo_client: ExpoClient | None = None):
        self.db = db
        self.expo_client = expo_client or get_expo_client()

    async def process_pending_receipts(self, limit: int = 500) -> int:
        """
        Poll Expo for pending push ticket receipts and persist final statuses.
        """
        pending_stmt = (
            select(ExpoPushReceipt)
            .options(selectinload(ExpoPushReceipt.admin_log))
            .where(ExpoPushReceipt.status.in_(["sent", "pending"]))
            .order_by(ExpoPushReceipt.created_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(pending_stmt)
        pending_rows: List[ExpoPushReceipt] = result.scalars().all()
        if not pending_rows:
            return 0

        ticket_ids = list({row.ticket_id for row in pending_rows if row.ticket_id})
        if not ticket_ids:
            return 0

        receipt_payload = await self.expo_client.get_push_receipts(ticket_ids)
        if not receipt_payload:
            return 0

        now = datetime.now(timezone.utc)
        processed = 0

        for row in pending_rows:
            receipt = receipt_payload.get(row.ticket_id)
            if not receipt:
                continue

            status = receipt.get("status")
            if status == "ok":
                row.status = "delivered"
                row.error_code = None
                row.error_message = None
                if row.admin_log:
                    row.admin_log.delivery_status = PushDeliveryStatus.DELIVERED
                    row.admin_log.failure_reason = None
            elif status == "error":
                details = receipt.get("details") or {}
                error_code = details.get("error")
                row.status = "failed"
                row.error_code = error_code
                row.error_message = receipt.get("message")

                if row.admin_log:
                    row.admin_log.delivery_status = PushDeliveryStatus.FAILED
                    row.admin_log.failure_reason = row.error_message or error_code or "Expo receipt failure"

                if error_code == "DeviceNotRegistered":
                    await self._invalidate_stale_token(
                        token=row.expo_push_token,
                        user_id=row.user_id,
                    )
            else:
                # Keep status unchanged if Expo has no final answer yet.
                continue

            row.checked_at = now
            processed += 1

        if processed:
            await self.db.commit()
        return processed

    async def _invalidate_stale_token(self, token: str | None, user_id: int | None = None) -> None:
        if not token:
            return

        device_stmt = select(PushDevice).where(
            PushDevice.expo_push_token == token,
            PushDevice.is_active == True,
        )
        device_result = await self.db.execute(device_stmt)
        devices = device_result.scalars().all()
        for device in devices:
            device.is_active = False
            device.invalidated_reason = "DeviceNotRegistered"

        if user_id:
            user = await self.db.get(User, user_id)
            if user and user.expo_push_token == token:
                user.expo_push_token = None
