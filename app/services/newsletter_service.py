from sqlalchemy.orm import Session
from sqlalchemy.future import select
from app.models.newsletter import Newsletter
from app.schemas.newsletter import NewsletterCreate, NewsletterUpdate
from fastapi import HTTPException

async def create_newsletter(db: Session, newsletter: NewsletterCreate):
    db_newsletter = Newsletter(subject=newsletter.subject, content=newsletter.content)
    db.add(db_newsletter)
    await db.commit()
    await db.refresh(db_newsletter)
    return db_newsletter

async def get_newsletters(db: Session):
    result = await db.execute(select(Newsletter))
    return result.scalars().all()

async def get_newsletter(db: Session, newsletter_id: int):
    result = await db.execute(select(Newsletter).filter(Newsletter.id == newsletter_id))
    db_newsletter = result.scalars().first()
    if not db_newsletter:
        raise HTTPException(status_code=404, detail="Newsletter not found")
    return db_newsletter

async def update_newsletter(db: Session, newsletter_id: int, newsletter: NewsletterUpdate):
    db_newsletter = await get_newsletter(db, newsletter_id)
    db_newsletter.subject = newsletter.subject
    db_newsletter.content = newsletter.content
    await db.commit()
    await db.refresh(db_newsletter)
    return db_newsletter

async def delete_newsletter(db: Session, newsletter_id: int):
    db_newsletter = await get_newsletter(db, newsletter_id)
    await db.delete(db_newsletter)
    await db.commit()
    return {"message": "Newsletter deleted"}
