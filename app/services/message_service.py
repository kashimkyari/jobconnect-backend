from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import or_, and_, desc, func, update
from typing import List, Optional
import json
from datetime import datetime, timezone

from ..schemas.message import Call, MessageType, Conversation
from ..websocket_manager import manager
from .notification_service import NotificationService
from ..services.message_presence import message_presence
from ..utils.url import generate_file_url
from ..models.message import Message
from ..models.user import User
from ..config import settings
from ..utils.filters import MessageFilter
from .system_message_service import SystemMessageService

class MessageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _serialize_message(message: Message) -> dict:
        return {
            "id": message.id,
            "content": message.content,
            "sender_id": message.sender_id,
            "receiver_id": message.receiver_id,
            "job_id": message.job_id,
            "application_id": message.application_id,
            "is_read": bool(message.is_read),
            "message_type": message.message_type,
            "created_at": message.created_at.isoformat() if message.created_at else None,
            "updated_at": message.updated_at.isoformat() if message.updated_at else None,
        }

    async def _emit_unread_count(self, user_id: int) -> None:
        count = await self.get_unread_count(user_id)
        await manager.send_personal_json(
            {
                "type": "message.unread_count",
                "payload": {"user_id": user_id, "count": count},
            },
            user_id,
        )

    async def _emit_message_new(self, message: Message) -> None:
        unread_for_receiver = await self.get_unread_count(message.receiver_id)
        payload = {
            "message": self._serialize_message(message),
            "conversation_user_id": message.sender_id,
            "unread_count": unread_for_receiver,
        }
        await manager.send_personal_json({"type": "message.new", "payload": payload}, message.receiver_id)
        await manager.send_personal_json({"type": "message.sent", "payload": payload}, message.sender_id)
        await self._emit_unread_count(message.receiver_id)

    async def emit_typing_event(self, sender_id: int, receiver_id: int, is_typing: bool) -> None:
        await manager.send_personal_json(
            {
                "type": "message.typing",
                "payload": {
                    "sender_id": sender_id,
                    "receiver_id": receiver_id,
                    "is_typing": is_typing,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            receiver_id,
        )

    async def _emit_read_receipt(self, reader_id: int, other_user_id: int, updated_count: int) -> None:
        payload = {
            "reader_id": reader_id,
            "other_user_id": other_user_id,
            "updated_count": int(updated_count or 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await manager.send_personal_json({"type": "message.read", "payload": payload}, other_user_id)
        await manager.send_personal_json({"type": "message.read", "payload": payload}, reader_id)
        await self._emit_unread_count(reader_id)
        await self._emit_unread_count(other_user_id)

    async def _send_message_push(self, message: Message) -> None:
        if message_presence.is_active(message.receiver_id, message.sender_id):
            return

        sender = await self.db.get(User, message.sender_id)
        receiver = await self.db.get(User, message.receiver_id)

        sender_name = "Someone"
        if sender:
            name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
            sender_name = name or sender_name

        avatar_url = ""
        if sender and sender.avatar_url:
            avatar_url = generate_file_url(sender.avatar_url)

        content = (message.content or "").strip()
        first_line = content.splitlines()[0].strip() if content else "You have a new message"
        body = first_line[:200]
        preview = content[:200]

        notif_service = NotificationService(self.db)
        payload = {
            "title": f"{sender_name} just messaged you",
            "body": body,
            "message": body,
            "subtitle": "JobConnect",
            "category": "messages",
            "type": "notification",
            "notification_type": "messages",
            "recipient_role": notif_service._as_role_value(receiver) if receiver else None,
            "action_screen": "Chat",
            "action_payload": {
                "conversation_id": message.sender_id,
                "message_id": message.id,
                "message_preview": preview,
                "sender_id": message.sender_id,
                "sender_name": sender_name,
                "sender_avatar": avatar_url,
                "image_url": avatar_url,
            },
            "conversation_id": message.sender_id,
            "message_id": message.id,
            "sender_name": sender_name,
            "sender_avatar": avatar_url,
            "image_url": avatar_url,
        }

        await notif_service.send_push_only(user_id=message.receiver_id, payload=payload)

    async def create_message(
        self,
        content: str,
        sender_id: int,
        receiver_id: int,
        message_type: str = "text",
        call_type: Optional[str] = None,
        file_id: Optional[int] = None,
        job_id: Optional[int] = None,
        application_id: Optional[int] = None,
        booking_id: Optional[int] = None,
        is_contract: bool = False,
    ) -> Message:
        effective_message_type = MessageType.CONTRACT if is_contract else message_type

        # Apply contact moderation only on regular user text messages.
        is_text_message = (
            effective_message_type == MessageType.TEXT
            or effective_message_type == MessageType.TEXT.value
        )
        is_system_sender = sender_id == settings.SYSTEM_USER_ID
        if is_text_message and not is_system_sender:
            has_contact, contact_type = MessageFilter.contains_contact_info(content)
            if has_contact:
                filtered_content, was_modified = MessageFilter.filter_message(content)
                message = Message(
                    content=filtered_content if was_modified else content,
                    sender_id=sender_id,
                    receiver_id=receiver_id,
                    message_type=effective_message_type,
                    call_type=call_type,
                    file_id=file_id,
                    job_id=job_id,
                    application_id=application_id,
                    booking_id=booking_id,
                )

                self.db.add(message)
                await self.db.commit()
                await self.db.refresh(message)

                # Notify users only when content is actually redacted.
                if was_modified:
                    system_message_service = SystemMessageService(self.db)
                    await system_message_service.create_and_send_system_message(
                        receiver_id=sender_id,
                        original_sender_id=sender_id,
                        message_type="contact_info_blocked_sender",
                        contact_type=contact_type
                    )
                    await system_message_service.create_and_send_system_message(
                        receiver_id=receiver_id,
                        original_sender_id=sender_id,
                        message_type="contact_info_blocked_receiver",
                        contact_type=contact_type
                    )

                await self._emit_message_new(message)

                try:
                    await self._send_message_push(message)
                except Exception:
                    pass

                return message

        # If no contact info, proceed as normal
        message = Message(
            content=content,
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_type=effective_message_type,
            call_type=call_type,
            file_id=file_id,
            job_id=job_id,
            application_id=application_id,
            booking_id=booking_id,
        )
        
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        await self._emit_message_new(message)

        try:
            await self._send_message_push(message)
        except Exception:
            pass

        return message

    async def get_conversation(
        self,
        user_id: int,
        other_user_id: int,
        skip: int = 0,
        limit: int = 50
    ) -> List[Message]:
        query = (
            select(Message)
            .options(
                selectinload(Message.sender),
                selectinload(Message.receiver)
            )
            .where(
                or_(
                    and_(
                        Message.sender_id == user_id,
                        Message.receiver_id == other_user_id
                    ),
                    and_(
                        Message.sender_id == other_user_id,
                        Message.receiver_id == user_id
                    )
                )
            )
            .order_by(desc(Message.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.db.execute(query)
        messages = result.scalars().all()

        # Opening a conversation marks all messages from that user as read.
        await self.mark_conversation_read(user_id=user_id, other_user_id=other_user_id)
        
        return messages

    async def get_unread_messages(self, user_id: int) -> List[Message]:
        query = (
            select(Message)
            .where(
                and_(
                    Message.receiver_id == user_id,
                    Message.is_read == False
                )
            )
            .order_by(desc(Message.created_at))
        )
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_unread_count(self, user_id: int) -> int:
        query = select(func.count(Message.id)).where(
            and_(
                Message.receiver_id == user_id,
                Message.is_read == False
            )
        )
        result = await self.db.execute(query)
        return int(result.scalar() or 0)

    async def mark_conversation_read(self, user_id: int, other_user_id: int) -> int:
        stmt = (
            update(Message)
            .where(
                and_(
                    Message.sender_id == other_user_id,
                    Message.receiver_id == user_id,
                    Message.is_read == False
                )
            )
            .values(is_read=True)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        updated_count = int(result.rowcount or 0)
        if updated_count > 0:
            await self._emit_read_receipt(reader_id=user_id, other_user_id=other_user_id, updated_count=updated_count)
        return updated_count

    async def mark_message_read(self, message_id: int, user_id: int) -> bool:
        message = await self.db.get(Message, message_id)
        
        if not message or message.receiver_id != user_id:
            return False
            
        message.is_read = True
        await self.db.commit()
        await self._emit_read_receipt(reader_id=user_id, other_user_id=message.sender_id, updated_count=1)
        return True

    async def get_conversations(self, user_id: int) -> List[Conversation]:
        # Get latest message with each user
        subquery = (
            select(Message)
            .where(
                or_(
                    Message.sender_id == user_id,
                    Message.receiver_id == user_id
                )
            )
            .order_by(desc(Message.created_at))
        )
        
        conversations = []
        seen_users = set()
        
        result = await self.db.execute(subquery)
        messages = result.scalars().all()
        
        for message in messages:
            other_user_id = (
                message.receiver_id
                if message.sender_id == user_id
                else message.sender_id
            )
            
            if other_user_id not in seen_users:
                other_user = await self.db.get(User, other_user_id)
                if other_user:
                    conversations.append(
                        Conversation(
                            user={
                                "id": other_user.id,
                                "first_name": other_user.first_name,
                                "last_name": other_user.last_name,
                                "avatar_url": other_user.avatar_url
                            },
                            last_message={
                                "content": message.content,
                                "created_at": message.created_at,
                                "is_read": message.is_read,
                                "sender_id": message.sender_id
                            }
                        )
                    )
                    seen_users.add(other_user_id)
                    
        return conversations

    async def delete_message(self, message_id: int, user_id: int) -> bool:
        message = await self.db.get(Message, message_id)
        
        if not message or message.sender_id != user_id:
            return False
            
        await self.db.delete(message)
        await self.db.commit()
        return True

    async def handle_call_message(self, call_data: Call):
        if call_data.type == "call-offer":
            content = "Started a call."
            message_type = MessageType.AUDIO_CALL
        elif call_data.type == "video-offer":
            content = "Started a video call."
            message_type = MessageType.VIDEO_CALL
        else:
            return

        new_message = await self.create_message(
            content=content,
            sender_id=call_data.sender_id,
            receiver_id=call_data.receiver_id,
            message_type=message_type,
        )
        
        # Notify the recipient
        await manager.send_personal_message(
            json.dumps(call_data.dict()),
            call_data.receiver_id
        )
        
        return new_message

    async def update_call_message(self, call_name: str, duration: int):
        query = (
            select(Message)
            .where(Message.content == f"Call started: {call_name}")
        )
        result = await self.db.execute(query)
        message = result.scalars().first()

        if message:
            message.call_duration = duration
            await self.db.commit()
