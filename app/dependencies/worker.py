from fastapi import Depends, HTTPException, status
from app.models.user import User
from app.services.auth_service import get_current_user

def get_current_worker(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "worker":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only accessible by workers."
        )
    return current_user
