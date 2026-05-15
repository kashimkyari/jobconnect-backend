from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional, Union
import logging

from app.database import get_db
from app.models.user import User, UserRole
from app.models.job import Job, JobStatus, JobLocationType
from app.models.service import Service
from app.models.category import Category
from app.models.review import Review
from app.models.dispute import Dispute
from app.models.notification import Notification
from app.models.file import File
from app.models.message import Message
from app.schemas.search import UnifiedSearchResponse, SearchResultType, SearchResult, MessageSearchResult
from app.schemas.review import ReviewInDB
from app.schemas.dispute import DisputeInDB
from app.schemas.notification import NotificationResponse
from app.schemas.job import JobInDB
from app.schemas.service import ServiceInDB
from app.schemas.user import UserProfileWithLocation
from app.utils.security import get_current_user
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["Search"])
logger = logging.getLogger(__name__)

@router.get("/", response_model=UnifiedSearchResponse)
async def unified_search(
    q: Optional[str] = Query(None, description="Search query string"),
    type: str = Query("All", description="Search type"),
    category_id: Optional[Union[str, int]] = Query(None, description="Filter by category"),
    min_price: Optional[float] = Query(None, description="Minimum price"),
    max_price: Optional[float] = Query(None, description="Maximum price"),
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
    radius_km: Optional[int] = Query(None, ge=1, le=500),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Refactored unified search endpoint using SearchService with FTS ranking."""
    try:
        search_data = await SearchService.unified_search(
            db=db, q=q, current_user_id=current_user.id, search_type=type,
            category_id=category_id, min_price=min_price, max_price=max_price,
            latitude=latitude, longitude=longitude, radius_km=radius_km,
            page=page, limit=limit
        )
        results = search_data["results"]
        
        # Secondary entities (Messages, Reviews, etc.) handled within "All" or specifically
        if q and type in ["All", "Messages", "Reviews", "Disputes", "Notifications"]:
            sec_limit = 5 if type == "All" else limit
            # Messages
            if type in ["All", "Messages"]:
                m_q = select(Message).where(or_(Message.sender_id == current_user.id, Message.receiver_id == current_user.id), Message.content.ilike(f"%{q}%")).order_by(Message.created_at.desc()).limit(sec_limit)
                m_res = await db.execute(m_q)
                for m in m_res.scalars().all():
                    results.append(SearchResult(type=SearchResultType.MESSAGE, data=MessageSearchResult(id=m.id, content=m.content, sender_name=m.sender.first_name if m.sender else "Unknown", created_at=m.created_at, conversation_id=m.conversation_id if hasattr(m, 'conversation_id') else None)))
            
            # Additional entities can be added here similarly if needed for "All" tab.
            # Keeping it lightweight for initially refactored version.

        return UnifiedSearchResponse(results=results, total_count=len(results), page=page, limit=limit)
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during search: {str(e)}"
        )
