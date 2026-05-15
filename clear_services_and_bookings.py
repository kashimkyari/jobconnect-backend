#!/usr/bin/env python3
"""
Clear all services and bookings from the database.

Usage:
  python clear_services_and_bookings.py
"""

import sys
from pathlib import Path
import asyncio

# Add the backend directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


async def clear_services_and_bookings():
    try:
        from app.config import settings
        from app.models.booking import Booking
        from app.models.review import Review
        from app.models.service import Service
        from app.models.story import Story, StoryView

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with async_session() as session:
            booking_count = (await session.execute(select(func.count()).select_from(Booking))).scalar() or 0
            service_count = (await session.execute(select(func.count()).select_from(Service))).scalar() or 0
            review_count = (await session.execute(select(func.count()).select_from(Review))).scalar() or 0
            story_count = (await session.execute(select(func.count()).select_from(Story))).scalar() or 0

            print(
                f"[INFO] Found {booking_count} bookings, {service_count} services, "
                f"{review_count} reviews, {story_count} stories."
            )

            # Delete dependents first to avoid FK constraints.
            await session.execute(delete(Booking))
            await session.execute(delete(Review).where(Review.service_id.is_not(None)))
            story_ids = select(Story.id).where(Story.service_id.is_not(None))
            await session.execute(delete(StoryView).where(StoryView.story_id.in_(story_ids)))
            await session.execute(delete(Story).where(Story.service_id.is_not(None)))
            await session.execute(delete(Service))
            await session.commit()

            print("[SUCCESS] Cleared all bookings and services.")

        await engine.dispose()
    except Exception as e:
        print(f"[ERROR] Failed to clear services/bookings: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(clear_services_and_bookings())
