from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..schemas.session import SessionResponse, SessionListResponse
from ..models.user_session import UserSession
from ..models.user import User
from ..database import get_db
from ..services.auth_service import get_current_user
from ..utils.logging import auth_logger

router = APIRouter()

@router.get("/", response_model=SessionListResponse)
async def get_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from ..utils.device_utils import get_client_ip
    
    query = select(UserSession).where(
        UserSession.user_id == current_user.id,
        UserSession.is_deleted == False
    ).order_by(UserSession.last_used_at.desc())
    
    result = await db.execute(query)
    sessions = result.scalars().all()
    
    # Simple heuristic to identify current session without passing session ID in JWT payload
    current_ip = get_client_ip(request)
    current_ua = request.headers.get("user-agent", "")
    
    session_responses = []
    has_current = False
    
    for s in sessions:
        # If we haven't found current yet, and matches IP + UA
        is_current = not has_current and (s.ip_address == current_ip) and (s.user_agent == current_ua)
        if is_current:
            has_current = True
            
        session_responses.append(SessionResponse(
            id=s.id,
            device_name=s.device_name,
            device_type=s.device_type,
            ip_address=s.ip_address,
            location=s.location,
            is_active=s.is_active,
            is_current=is_current,
            last_used_at=s.last_used_at,
            created_at=s.created_at,
            expires_at=s.expires_at
        ))
        
    return SessionListResponse(sessions=session_responses)

@router.put("/{session_id}/revoke")
async def revoke_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    session = await db.get(UserSession, session_id)
    if not session or session.user_id != current_user.id or session.is_deleted:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session.is_active = False
    await db.commit()
    
    auth_logger.info(f"Session {session_id} revoked by user {current_user.id}")
    return {"message": "Session revoked successfully"}

@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    session = await db.get(UserSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session.is_active = False
    session.is_deleted = True
    await db.commit()
    
    auth_logger.info(f"Session {session_id} deleted by user {current_user.id}")
    return {"message": "Session deleted successfully"}

@router.delete("/")
async def revoke_all_other_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from ..utils.device_utils import get_client_ip
    current_ip = get_client_ip(request)
    current_ua = request.headers.get("user-agent", "")
    
    query = select(UserSession).where(
        UserSession.user_id == current_user.id,
        UserSession.is_deleted == False
    )
    result = await db.execute(query)
    sessions = result.scalars().all()
    
    revoked_count = 0
    has_kept_one = False
    for s in sessions:
        # Keep the session matching IP and UA
        if not has_kept_one and s.ip_address == current_ip and s.user_agent == current_ua:
            has_kept_one = True
            continue
            
        s.is_active = False
        revoked_count += 1
        
    if revoked_count > 0:
        await db.commit()
        
    auth_logger.info(f"User {current_user.id} revoked {revoked_count} other sessions")
    return {"message": f"Successfully revoked {revoked_count} other sessions"}
