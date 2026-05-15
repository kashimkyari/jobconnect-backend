from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import List, Optional
from fastapi import HTTPException, status

from ..models.category import Category

class CategoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_categories(self, skip: int = 0, limit: int = 10) -> List[Category]:
        query = select(Category).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_all_categories(self) -> List[Category]:
        """Get all categories without pagination"""
        query = select(Category)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_category_by_id(self, category_id: int) -> Optional[Category]:
        """Get a category by ID"""
        query = select(Category).where(Category.id == category_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_category_by_name(self, name: str) -> Optional[Category]:
        """Get a category by name"""
        query = select(Category).where(Category.name == name)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def create_category(self, name: str) -> Category:
        """Create a new category"""
        # Check if category already exists
        existing = await self.get_category_by_name(name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category with this name already exists"
            )
        
        category = Category(name=name)
        self.db.add(category)
        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def update_category(self, category_id: int, name: str) -> Optional[Category]:
        """Update a category"""
        category = await self.get_category_by_id(category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )
        
        # Check if new name already exists (and is not the current category)
        existing = await self.get_category_by_name(name)
        if existing and existing.id != category_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category with this name already exists"
            )
        
        category.name = name
        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def delete_category(self, category_id: int) -> bool:
        """Delete a category"""
        category = await self.get_category_by_id(category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )
        
        await self.db.delete(category)
        await self.db.commit()
        return True

    async def get_category_count(self) -> int:
        """Get total count of categories"""
        query = select(func.count(Category.id))
        result = await self.db.execute(query)
        return result.scalar()
