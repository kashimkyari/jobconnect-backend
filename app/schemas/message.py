from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class Call(BaseModel):
    type: str
    sender_id: int
    receiver_id: int
    data: Optional[Dict[str, Any]] = None

class MessageType(str, Enum):
    TEXT = "text"
    FILE = "file"
    SYSTEM = "system"
    AUDIO_CALL = "audio_call"
    VIDEO_CALL = "video_call"
    CONTRACT = "contract"

# Base Schema
class MessageBase(BaseModel):
    content: str = Field(..., min_length=1)
    message_type: MessageType = Field(default=MessageType.TEXT)
    file_id: Optional[int] = None

# Request Schemas
class MessageCreate(MessageBase):
    receiver_id: int
    job_id: Optional[int] = None
    application_id: Optional[int] = None

class MessageUpdate(BaseModel):
    is_read: bool

# Response Schemas
class MessageInDB(MessageBase):
    id: int
    sender_id: int
    receiver_id: int
    job_id: Optional[int] = None
    application_id: Optional[int] = None
    is_read: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ConversationUser(BaseModel):
    id: int
    first_name: str
    last_name: str
    avatar_url: Optional[str] = None

class LastMessage(BaseModel):
    content: str
    created_at: datetime
    is_read: bool
    sender_id: int

class Conversation(BaseModel):
    user: ConversationUser
    last_message: LastMessage

class ConversationSummary(BaseModel):
    other_user_id: int
    other_user_name: str
    other_user_avatar: Optional[str]
    last_message: str
    last_message_time: datetime
    unread_count: int

class MessageWithUser(MessageInDB):
    sender_name: str
    sender_avatar: Optional[str]
    receiver_name: str
    receiver_avatar: Optional[str]
