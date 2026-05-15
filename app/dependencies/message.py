from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.message_service import MessageService
from ..database import get_db


async def get_message_service(
    db: AsyncSession = Depends(get_db),
) -> MessageService:
    return MessageService(db)
