from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app import schemas
from app.database import get_db
from app.models.user import User
from app.models.bank_account import BankAccount
from app.services.auth_service import get_current_user
from sqlalchemy.future import select

router = APIRouter()

@router.post("", response_model=schemas.bank_account.BankAccountInDB)
async def add_bank_account(
    bank_account_in: schemas.bank_account.BankAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add a new bank account for the current user.
    """
    bank_account = BankAccount(
        **bank_account_in.dict(), user_id=current_user.id
    )
    db.add(bank_account)
    await db.commit()
    await db.refresh(bank_account)
    return bank_account

@router.get("", response_model=List[schemas.bank_account.BankAccountInDB])
async def get_saved_banks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all saved bank accounts for the current user.
    """
    result = await db.execute(
        select(BankAccount).where(BankAccount.user_id == current_user.id)
    )
    return result.scalars().all()
