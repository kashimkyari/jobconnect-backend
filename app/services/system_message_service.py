from sqlalchemy.ext.asyncio import AsyncSession
from ..models.message import Message
from ..config import settings

class SystemMessageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_and_send_system_message(
        self,
        receiver_id: int,
        original_sender_id: int,
        message_type: str,
        contact_type: str
    ):
        if message_type == "contact_info_blocked_sender":
            content = (
                "Your message was blocked because it contained a "
                f"{contact_type}. Please do not share contact information "
                "directly. All communication should be kept on the "
                "JobConnect platform."
            )
        elif message_type == "contact_info_blocked_receiver":
            content = (
                "A message sent to you was blocked because it contained a "
                f"{contact_type}. Please remind the sender to keep all "
                "communication on the JobConnect platform."
            )
        else:
            return

        system_message = Message(
            content=content,
            sender_id=settings.SYSTEM_USER_ID,
            receiver_id=receiver_id,
            message_type="system"
        )
        
        self.db.add(system_message)
        await self.db.commit()
        await self.db.refresh(system_message)
