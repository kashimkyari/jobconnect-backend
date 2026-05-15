from pydantic import BaseModel
from datetime import datetime

class NewsletterBase(BaseModel):
    subject: str
    content: str

class NewsletterCreate(NewsletterBase):
    pass

class NewsletterUpdate(NewsletterBase):
    pass

class Newsletter(NewsletterBase):
    id: int
    publication_date: datetime
    created_at: datetime

    class Config:
        from_attributes = True
