from pydantic import BaseModel

class BadgeBase(BaseModel):
    name: str
    description: str
    icon_url: str | None = None
    criteria_type: str
    criteria_value: float

class BadgeCreate(BadgeBase):
    pass

class Badge(BadgeBase):
    id: int

    class Config:
        from_attributes = True
