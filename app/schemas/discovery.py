"""
Discovery-related schemas for area intelligence and provider browsing
"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class TrendingCategoryResponse(BaseModel):
    """Response for a single trending category"""
    id: int
    name: str
    icon: Optional[str] = None
    job_count: int
    service_count: int
    total_count: int
    avg_rating: float
    demand_trend: str  # "high", "medium", "low"
    
    class Config:
        from_attributes = True


class AreaStatsResponse(BaseModel):
    """Area statistics"""
    total_service_providers: int
    total_open_jobs: int
    avg_provider_rating: float


class AreaLocationResponse(BaseModel):
    """Location information for area summary"""
    latitude: float
    longitude: float
    radius_km: int


class AreaSummaryResponse(BaseModel):
    """Complete area summary response"""
    location: AreaLocationResponse
    stats: AreaStatsResponse
    trending_categories: List[TrendingCategoryResponse]
    demand_signals: str


class ProviderProfileResponse(BaseModel):
    """Provider profile for browsing (guest-friendly)"""
    id: int
    service_id: int
    name: str
    avatar_url: Optional[str] = None
    title: str  # Service name/title
    description: Optional[str] = None
    rating: float
    review_count: int
    response_time_hours: int
    certifications: List[str] = []
    distance_km: float
    is_verified: bool
    price: float
    pricing_model: str
    
    class Config:
        from_attributes = True


class WorkerProfileResponse(BaseModel):
    """Worker profile for browsing (guest-friendly)"""
    id: int
    name: str
    avatar_url: Optional[str] = None
    reputation_score: float
    is_verified: bool
    distance_km: float
    
    class Config:
        from_attributes = True


class BrowseByCategoryResponse(BaseModel):
    """Response for browsing providers by category"""
    category_id: int
    category_name: str
    providers: List[ProviderProfileResponse]
    total_count: int


class DiscoveryFeedItem(BaseModel):
    """Single item in a discovery feed"""
    id: int
    type: str  # "service", "worker", "trending_category"
    title: str
    description: Optional[str] = None
    metadata: Dict[str, Any] = {}
