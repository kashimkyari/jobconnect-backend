from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .database import async_session
import asyncio
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def expire_stories_job():
    """
    Scheduled job to expire stories older than 24 hours.
    Runs every 30 minutes.
    """
    async with async_session() as session:
        try:
            from app.services.story_service import StoryService
            expired_count = await StoryService.expire_old_stories(session)
            logger.info(f"Story expiry job completed: {expired_count} stories expired")
        except Exception as e:
            logger.error(f"Error in story expiry job: {str(e)}")


async def process_push_receipts_job():
    """
    Poll Expo for pending push receipts and update delivery status.
    Runs every 5 minutes.
    """
    async with async_session() as session:
        try:
            from app.services.push_receipt_service import PushReceiptService

            processed = await PushReceiptService(session).process_pending_receipts(limit=500)
            if processed:
                logger.info(f"Push receipts job completed: {processed} receipts updated")
        except Exception as e:
            logger.error(f"Error in push receipts job: {str(e)}")


def init_scheduler():
    """
    Initializes the scheduler with background jobs.
    """
    # Story expiry job - runs every 30 minutes
    scheduler.add_job(expire_stories_job, "interval", minutes=30, id="expire_stories_job")
    scheduler.add_job(
        process_push_receipts_job,
        "interval",
        minutes=5,
        id="process_push_receipts_job",
    )
    
    scheduler.start()
    logger.info("Scheduler initialized with jobs")
