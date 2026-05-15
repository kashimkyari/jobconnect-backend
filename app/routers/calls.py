"""
Stream Chat API routes for voice and video calling integration.
Handles token generation and call management.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import datetime, timedelta
import logging
from typing import Any, Dict

from ..config import settings
from ..services.auth_service import get_current_user
from ..services.message_service import MessageService
from ..dependencies.message import get_message_service
from stream_chat import StreamChat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])


class TokenRequest(BaseModel):
    """Request model for token generation"""
    user_id: str


class TokenResponse(BaseModel):
    """Response model for token generation"""
    token: str
    user_id: str
    expires_at: str


class CallInitiationRequest(BaseModel):
    """Request model for initiating a call"""
    call_name: str
    target_user_id: str
    call_type: str  # 'audio' or 'video'


class CreateCallRequest(BaseModel):
    """Request model for creating a call"""
    call_name: str
    target_user_id: str
    call_type: str
    call_settings: dict


class UpsertUserRequest(BaseModel):
    """Request model for upserting a user in Stream"""
    user_id: str
    user_name: str
    user_image: str


@router.post("/get-token", response_model=TokenResponse)
async def get_stream_token(
    request: TokenRequest,
    current_user = Depends(get_current_user)
):
    """
    Generate a Stream Chat token for the authenticated user.
    
    This token is required to connect to Stream Chat API for voice/video calling.
    
    Args:
        request: TokenRequest containing user_id
        current_user: Current authenticated user
        
    Returns:
        TokenResponse with token, api_key, and expiration
        
    Raises:
        HTTPException: If token generation fails
    """
    try:
        # Verify that the requested user_id matches the current user
        if str(request.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot generate token for another user"
            )
        
        # Initialize Stream Chat client
        client = StreamChat(
            api_key=settings.STREAM_CHAT_API_KEY,
            api_secret=settings.STREAM_CHAT_API_SECRET
        )
        
        # Ensure user exists in Stream
        client.upsert_user({
            "id": str(current_user.id),
            "name": current_user.first_name or current_user.email,
            "role": "user",
        })
        
        # Create token with 1 hour expiration
        token = client.create_token(request.user_id, expiration=3600)
        
        expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        
        logger.info(f"Generated Stream token for user {request.user_id}")
        
        return TokenResponse(
            token=token,
            user_id=request.user_id,
            expires_at=expires_at
        )
        
    except Exception as e:
        logger.error(f"Failed to generate Stream token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authentication token"
        )


@router.post("/upsert-user")
async def upsert_stream_user(
    request: UpsertUserRequest,
    current_user = Depends(get_current_user)
):
    """
    Create or update a user in Stream.
    """
    try:
        client = StreamChat(
            api_key=settings.STREAM_CHAT_API_KEY,
            api_secret=settings.STREAM_CHAT_API_SECRET
        )
        client.upsert_user({
            "id": request.user_id,
            "name": request.user_name,
            "image": request.user_image,
            "role": "user",
        })
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Failed to upsert Stream user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upsert user in Stream"
        )


@router.post("/create-call")
async def create_stream_call(
    request: CreateCallRequest,
    current_user = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
) -> Dict[str, str]:
    """
    Create a call channel and send an invitation message.
    """
    try:
        client = StreamChat(
            api_key=settings.STREAM_CHAT_API_KEY,
            api_secret=settings.STREAM_CHAT_API_SECRET
        )

        channel = client.channel('messaging', request.call_name, {
            "members": [str(current_user.id), request.target_user_id],
        })

        channel.create(str(current_user.id))

        channel.send_message({
            "text": f"Incoming {request.call_type} call from {current_user.first_name or current_user.email}",
            "custom": {
                "type": "call_invite",
                "call_type": request.call_type,
                "call_name": request.call_name,
                "settings": request.call_settings,
            },
        }, str(current_user.id))

        try:
            target_user_id = int(request.target_user_id)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid target_user_id"
            )

        message_type = "video_call" if request.call_type == "video" else "audio_call"

        await message_service.create_message(
            sender_id=current_user.id,
            receiver_id=target_user_id,
            content=f"Call started: {request.call_name}",
            message_type=message_type,
            call_type=request.call_type,
        )

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Failed to create Stream call: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create call"
        )


@router.post("/initialize-call")
async def initialize_call(
    request: CallInitiationRequest,
    current_user = Depends(get_current_user)
):
    """
    Initialize a call between two users.
    
    This endpoint creates the necessary backend state for a call.
    The actual call connection happens through Stream Chat client.
    
    Args:
        request: CallInitiationRequest with call details
        current_user: Current authenticated user
        
    Returns:
        Call initialization status
    """
    try:
        # Log call initiation for analytics
        logger.info(
            f"Call initiated from {current_user.id} to {request.target_user_id} "
            f"(type: {request.call_type})"
        )
        
        return {
            "status": "initialized",
            "call_name": request.call_name,
            "caller_id": current_user.id,
            "callee_id": request.target_user_id,
            "call_type": request.call_type,
            "created_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to initialize call: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize call"
        )


@router.post("/end-call")
async def end_call(
    call_name: str,
    duration: int,
    current_user = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
) -> Dict[str, Any]:
    """
    End an active call.
    
    This endpoint logs the call end and cleans up backend state.
    
    Args:
        call_name: Name of the call to end
        current_user: Current authenticated user
        
    Returns:
        Call end status
    """
    try:
        logger.info(f"Call {call_name} ended by user {current_user.id}")
        
        await message_service.update_call_message(
            call_name=call_name,
            duration=duration,
        )
        
        return {
            "status": "ended",
            "call_name": call_name,
            "ended_at": datetime.utcnow().isoformat(),
            "ended_by": current_user.id
        }
        
    except Exception as e:
        logger.error(f"Failed to end call: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to end call"
        )


@router.get("/health")
async def call_service_health():
    """Check if call service is operational"""
    try:
        client = StreamChat(
            api_key=settings.STREAM_CHAT_API_KEY,
            api_secret=settings.STREAM_CHAT_API_SECRET
        )
        # Test connection
        app_config = client.app_setting()
        
        return {
            "status": "healthy",
            "service": "stream_chat_calls",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Call service health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "service": "stream_chat_calls",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
