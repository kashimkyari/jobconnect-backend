from pydantic import BaseModel
from typing import List, Optional, Union, Any
from enum import Enum
from .job import JobInDB
from .service import ServiceInDB
from .user import UserProfileWithLocation
from .review import ReviewInDB
from .dispute import DisputeInDB
from .notification import NotificationResponse

class SearchResultType(str, Enum):
    JOB = "job"
    SERVICE = "service"
    WORKER = "worker"
    MESSAGE = "message"
    REVIEW = "review"
    DISPUTE = "dispute"
    NOTIFICATION = "notification"

class MessageSearchResult(BaseModel):
    id: int
    content: str
    sender_name: str
    conversation_id: Optional[int] = None
    created_at: Any

class SearchResult(BaseModel):
    type: SearchResultType
    data: Union[JobInDB, ServiceInDB, UserProfileWithLocation, MessageSearchResult, ReviewInDB, DisputeInDB, NotificationResponse]

class UnifiedSearchResponse(BaseModel):
    results: List[SearchResult]
    total_count: int
    page: int
    limit: int
