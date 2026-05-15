from pydantic import BaseModel, HttpUrl, field_validator
from typing import Optional, List
from app.utils.url import generate_file_url

# Schemas for RecentWork
class RecentWorkBase(BaseModel):
    description: str
    image_url: str

class RecentWorkCreate(RecentWorkBase):
    pass

class RecentWorkUpdate(BaseModel):
    description: Optional[str] = None
    image_url: Optional[str] = None

class RecentWorkInDB(RecentWorkBase):
    id: int
    user_id: int

    @field_validator("image_url", mode="before")
    @classmethod
    def make_image_url_absolute(cls, v: str) -> str:
        if not v:
            return None
        return generate_file_url(v)

    class Config:
        from_attributes = True

# Schemas for UserService
class UserServiceBase(BaseModel):
    service_name: Optional[str] = None

class UserServiceCreate(UserServiceBase):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    
    @field_validator("service_name", mode="before")
    @classmethod
    def set_service_name_from_title(cls, v, info):
        # If title is provided but service_name is not, use title as service_name
        if not v and info.data.get("title"):
            return info.data["title"]
        return v

class UserServiceUpdate(BaseModel):
    service_name: Optional[str] = None

class UserServiceInDB(UserServiceBase):
    id: int
    user_id: int
    service_id: Optional[int] = None
    description: Optional[str] = None
    price: Optional[float] = None
    pricing_model: Optional[str] = None
    estimated_delivery_time: Optional[str] = None
    revisions: Optional[int] = None
    tags: Optional[List[str]] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    image_url: Optional[str] = None
    total_reviews: Optional[int] = 0
    average_rating: Optional[float] = 0.0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True

# Schemas for Featured Services on Employer Home Screen
class ServiceShowcaseWorker(BaseModel):
    id: int
    first_name: str
    last_name: str
    avatar_url: Optional[str] = None
    headline: Optional[str] = None
    rating: Optional[float] = None
    total_reviews: Optional[int] = None

    class Config:
        from_attributes = True

class ServiceShowcaseItem(BaseModel):
    id: int
    name: str
    description: str
    price: float
    pricing_model: str
    estimated_delivery_time: Optional[str] = None
    revisions: Optional[int] = None
    tags: Optional[list] = None
    category_id: int
    category_name: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[list] = None
    worker: ServiceShowcaseWorker

    class Config:
        from_attributes = True
