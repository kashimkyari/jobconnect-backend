from sqlalchemy.orm import Session
from sqlalchemy.future import select
from app.models.waitlist import Waitlist
from app.schemas.waitlist import WaitlistCreate
from fastapi import HTTPException

async def add_to_waitlist(db: Session, waitlist_user: WaitlistCreate):
    result = await db.execute(select(Waitlist).filter(Waitlist.email == waitlist_user.email))
    db_user = result.scalars().first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already on the waitlist")
    db_waitlist_user = Waitlist(
        first_name=waitlist_user.first_name,
        last_name=waitlist_user.last_name,
        email=waitlist_user.email,
        user_type=waitlist_user.user_type,
        location=waitlist_user.location,
        newsletter=waitlist_user.newsletter,
    )
    db.add(db_waitlist_user)
    await db.commit()
    await db.refresh(db_waitlist_user)
    return db_waitlist_user

async def get_waitlist_users(db: Session):
    result = await db.execute(select(Waitlist))
    return result.scalars().all()

async def remove_from_waitlist(db: Session, email: str):
    result = await db.execute(select(Waitlist).filter(Waitlist.email == email))
    db_user = result.scalars().first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found on the waitlist")
    await db.delete(db_user)
    await db.commit()
    return {"message": "User removed from the waitlist"}
