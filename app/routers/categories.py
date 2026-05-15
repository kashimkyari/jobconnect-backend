from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..schemas.category import CategoryInDB
from ..services.category_service import CategoryService
from ..database import get_db

router = APIRouter()

@router.get("/", response_model=List[CategoryInDB])
async def list_categories(
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    category_service = CategoryService(db)
    categories = await category_service.get_categories(skip=skip, limit=limit)
    return categories
