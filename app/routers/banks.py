from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import httpx

from app.config import settings
from app.services.paystack_service import PaystackService

router = APIRouter()

@router.get("/banks", response_model=List[dict])
async def get_banks():
    """
    Get a list of all supported banks in Nigeria.
    """
    url = "https://api.paystack.co/bank?currency=NGN"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not fetch banks from Paystack.")
        return response.json()["data"]

@router.post("/resolve-account")
async def resolve_account(account_number: str, bank_code: str):
    """
    Resolves a bank account.
    """
    paystack_service = PaystackService()
    try:
        data = await paystack_service.verify_account(account_number, bank_code)
        return data
    except HTTPException as e:
        raise e
