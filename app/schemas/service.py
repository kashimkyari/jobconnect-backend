from pydantic import BaseModel, field_validator
from typing import List, Optional, Union
from app.models.enums import PricingModel

# Schemas for Service
class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    pricing_model: PricingModel = PricingModel.FIXED_PRICE
    estimated_delivery_time: Optional[str] = None
    revisions: Optional[int] = 1
    tags: Optional[List[str]] = []
    city: Optional[str] = None  # e.g., "Lagos", "Abuja"
    country: Optional[str] = "Nigeria"
    latitude: Optional[float] = None  # GPS latitude coordinate
    longitude: Optional[float] = None  # GPS longitude coordinate

class ServiceCreate(ServiceBase):
    category_id: Union[str, int]
    image_ids: Optional[List[int]] = []

    @field_validator('category_id', mode='before')
    @classmethod
    def validate_category_id(cls, v):
        """Validate category_id is a non-empty string or positive integer."""
        if isinstance(v, int):
            if v <= 0:
                raise ValueError('category_id must be a positive integer or non-empty string')
            return v
        if isinstance(v, str):
            if not v or not v.strip():
                raise ValueError('category_id must be a non-empty string')
            return v.strip()
        raise ValueError('category_id must be a string or integer')

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    pricing_model: Optional[PricingModel] = None
    estimated_delivery_time: Optional[str] = None
    revisions: Optional[int] = None
    tags: Optional[List[str]] = None
    category_id: Optional[Union[str, int]] = None
    city: Optional[str] = None
    country: Optional[str] = None

    @field_validator('category_id', mode='before')
    @classmethod
    def validate_category_id(cls, v):
        """Validate category_id is a non-empty string or positive integer."""
        if v is None:
            return None
        if isinstance(v, int):
            if v <= 0:
                raise ValueError('category_id must be a positive integer or non-empty string')
            return v
        if isinstance(v, str):
            if not v or not v.strip():
                raise ValueError('category_id must be a non-empty string')
            return v.strip()
        raise ValueError('category_id must be a string or integer')

class ServiceInDB(ServiceBase):
    id: int
    worker_id: int
    category_id: int
    last_request_id: Optional[str] = None
    category_name: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[List] = None
    total_orders: Optional[int] = None
    latitude: Optional[float] = None  # GPS latitude coordinate
    longitude: Optional[float] = None  # GPS longitude coordinate
    distance_km: Optional[float] = None  # Distance in km from requester's location
    distance_display: Optional[str] = None  # Formatted distance string

    class Config:
        from_attributes = True

# Schemas for ServiceCategory
class ServiceCategoryBase(BaseModel):
    name: str
    description: Optional[str] = None

class ServiceCategoryCreate(ServiceCategoryBase):
    pass

class ServiceCategoryUpdate(ServiceCategoryBase):
    name: Optional[str] = None
    description: Optional[str] = None

class ServiceCategoryInDB(ServiceCategoryBase):
    id: int

    class Config:
        from_attributes = True

class ServiceCategoryWithServices(ServiceCategoryInDB):
    services: List[ServiceInDB] = []

# Enriched service detail schema
class WorkerSummary(BaseModel):
    id: int
    first_name: str
    last_name: str
    avatar_url: Optional[str] = None
    rating: float  # reputation_score
    total_reviews: int
    completion_rate: Optional[float] = None  # percentage 0-100
    response_time_hours: Optional[float] = None  # average hours to respond
    
    class Config:
        from_attributes = True


class ReviewSummary(BaseModel):
    id: int
    rating: float
    comment: Optional[str] = None
    reviewer_first_name: Optional[str] = None
    created_at: Optional[str] = None
    
    class Config:
        from_attributes = True


class ServiceDetailResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    price: float
    pricing_model: str
    estimated_delivery_time: Optional[str] = None
    revisions: Optional[int] = 1
    tags: Optional[List[str]] = []
    city: Optional[str] = None
    country: Optional[str] = "Nigeria"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    category_id: int
    category_name: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[List] = None
    worker: Optional[WorkerSummary] = None
    reviews: Optional[List[ReviewSummary]] = None
    total_reviews: int = 0
    average_rating: float = 0.0
    created_at: Optional[str] = None
    
    class Config:
        from_attributes = True
