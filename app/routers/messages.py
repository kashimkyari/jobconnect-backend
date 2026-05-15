from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import json

from ..websocket_manager import manager
from ..models.user import User
from ..schemas.message import MessageCreate, MessageInDB, Call, Conversation
from ..services.message_service import MessageService
from ..database import async_session, get_db
from ..utils.security import get_current_user, get_current_user_for_websocket
from ..services.message_presence import message_presence

router = APIRouter()

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    token: str = Query(...),
):
    db = async_session()
    user = await get_current_user_for_websocket(token, db)
    if not user or user.id != int(user_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        await db.close()
        return

    await manager.connect(user_id, websocket)
    message_service = MessageService(db)
    await manager.send_personal_json(
        {"type": "connected", "payload": {"channel": "messages", "user_id": user_id}},
        user_id,
    )
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            event_type = payload.get("type")
            receiver_id = payload.get("receiver_id")

            if event_type in ["call-offer", "video-offer"]:
                call_data = Call(**payload)
                await message_service.handle_call_message(call_data)
            elif event_type == "typing_start" and receiver_id:
                await message_service.emit_typing_event(
                    sender_id=user_id,
                    receiver_id=int(receiver_id),
                    is_typing=True,
                )
            elif event_type == "typing_stop" and receiver_id:
                await message_service.emit_typing_event(
                    sender_id=user_id,
                    receiver_id=int(receiver_id),
                    is_typing=False,
                )
            elif event_type == "conversation_active":
                other_user_id = payload.get("other_user_id")
                if other_user_id:
                    message_presence.set_active(user_id, int(other_user_id))
            elif event_type == "conversation_inactive":
                message_presence.clear(user_id)
            else:
                # Handle signaling messages (answer, ice-candidate, etc.) as passthrough.
                if receiver_id:
                    await manager.send_personal_message(data, int(receiver_id))
                
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    except Exception as e:
        print(f"[messages.ws] unexpected error for user {user_id}: {e}")
    finally:
        manager.disconnect(user_id, websocket)
        message_presence.clear(user_id)
        await db.close()

@router.post("/", response_model=MessageInDB, status_code=status.HTTP_201_CREATED)
async def send_message(
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    message_service = MessageService(db)
    new_message = await message_service.create_message(
        content=message.content,
        sender_id=current_user.id,
        receiver_id=message.receiver_id,
        message_type=message.message_type,
        file_id=message.file_id,
        job_id=message.job_id,
        application_id=message.application_id,
    )
    return new_message

@router.get("/conversations", response_model=List[Conversation])
async def get_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    message_service = MessageService(db)
    conversations = await message_service.get_conversations(current_user.id)
    return conversations

@router.get("/unread", response_model=List[MessageInDB])
async def get_unread_messages(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    message_service = MessageService(db)
    messages = await message_service.get_unread_messages(current_user.id)
    return messages

@router.get("/unread/count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    message_service = MessageService(db)
    count = await message_service.get_unread_count(current_user.id)
    return {"count": count}

@router.put("/{message_id}/read")
async def mark_message_read(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    message_service = MessageService(db)
    success = await message_service.mark_message_read(message_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
        
    return {"status": "message marked as read"}

@router.put("/conversations/{other_user_id}/read-all")
async def mark_conversation_read(
    other_user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    message_service = MessageService(db)
    updated_count = await message_service.mark_conversation_read(
        user_id=current_user.id,
        other_user_id=other_user_id
    )
    return {"status": "conversation marked as read", "updated_count": updated_count}

@router.get("/{user_id}", response_model=List[MessageInDB])
async def get_user_messages(
    user_id: int,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all messages exchanged with specific user."""
    message_service = MessageService(db)
    messages = await message_service.get_conversation(
        user_id=current_user.id, other_user_id=user_id, skip=skip, limit=limit
    )
    return messages
