#!/usr/bin/env python3
"""
Seed categories into the database.
Run this after setting up the database to populate service categories.

Usage:
  python seed_categories.py
"""

import os
import sys
from pathlib import Path

# Add the backend directory to the path
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

# List of categories matching the frontend app categories
CATEGORIES = [
    "Healthcare",
    "Cleaning", 
    "Tutoring",
    "Logistics",
    "Web Development",
    "Graphic Design",
    "Writing & Content",
    "Photography",
    "Plumbing & Handyman",
    "Consulting",
    "Marketing",
    "Video Production",
    "Pet Care",
    "Fitness & Training",
    "Event Planning",
]


async def seed_categories():
    """Seed categories into the database."""
    try:
        from app.models.category import Category
        from app.config import settings
        
        # Create async engine
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        
        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with async_session() as session:
            print("[INFO] Checking existing categories...")
            
            for category_name in CATEGORIES:
                # Check if category already exists
                result = await session.execute(
                    select(Category).filter(Category.name == category_name)
                )
                existing = result.scalars().first()
                
                if existing:
                    print(f"[OK] Category '{category_name}' already exists (ID: {existing.id})")
                else:
                    # Create new category
                    new_category = Category(name=category_name)
                    session.add(new_category)
                    await session.flush()
                    print(f"[OK] Created category '{category_name}' (ID: {new_category.id})")
            
            # Commit all changes
            await session.commit()
            print("\n[SUCCESS] All categories have been seeded!")
        
        await engine.dispose()
        
    except Exception as e:
        print(f"[ERROR] Failed to seed categories: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(seed_categories())
