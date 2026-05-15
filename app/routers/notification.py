from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import logging
from app.schemas.notification import NotificationResponse
from app.websocket_manager import manager
from app.services.notification_service import NotificationService
from app.database import get_db, async_session
from app.services.auth_service import get_current_user
from app.utils.security import get_current_user_for_websocket
from app.models.user import User

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = logging.getLogger(__name__)

@router.get("/", response_model=List[NotificationResponse])
async def get_user_notifications(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all notifications for the current user, sorted by most recent.
    """
    notif_service = NotificationService(db)
    return await notif_service.get_user_notifications(current_user.id, skip, limit)

@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get a specific notification by ID.
    - **notification_id**: ID of the notification to retrieve.
    """
    notif_service = NotificationService(db)
    notification = await notif_service.get_notification_by_id(notification_id)
    if not notification or notification.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification

@router.put("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark a single notification as read.
    - **notification_id**: ID of the notification to mark as read.
    """
    notif_service = NotificationService(db)
    notification = await notif_service.mark_notification_as_read(notification_id, current_user.id)
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found or you do not have permission to update it."
        )
    return notification

@router.put("/read/all", status_code=status.HTTP_200_OK)
async def mark_all_as_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark all unread notifications for the current user as read.
    """
    notif_service = NotificationService(db)
    updated_count = await notif_service.mark_all_notifications_as_read(current_user.id)
    return {"message": f"Successfully marked {updated_count} notifications as read."}

@router.get("/unread/count", status_code=status.HTTP_200_OK)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get unread notification count for the current user.
    """
    notif_service = NotificationService(db)
    unread_count = await notif_service.get_unread_notification_count(current_user.id)
    return {"count": unread_count}

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
):
    token = websocket.query_params.get("token")
    db = async_session()
    current_user = await get_current_user_for_websocket(token, db)
    if current_user is None:
        logger.warning("Notifications WS rejected: missing/invalid token")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        await db.close()
        return

    logger.info("Notifications WS connected: user_id=%s", current_user.id)
    await manager.connect(current_user.id, websocket)
    try:
        while True:
            # This keeps the connection alive. We are not expecting client messages here.
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("Notifications WS disconnected: user_id=%s", current_user.id)
        manager.disconnect(current_user.id, websocket)
    finally:
        await db.close()
