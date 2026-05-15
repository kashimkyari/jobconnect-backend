from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app import schemas
from app.database import get_db
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.transaction_service import TransactionService

router = APIRouter()

@router.get("/all", response_model=List[schemas.transaction.TransactionInDB])
async def read_all_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve all transactions for the current user.
    """
    transaction_service = TransactionService(db)
    transactions = await transaction_service.get_user_transactions(current_user.id)
    return transactions
