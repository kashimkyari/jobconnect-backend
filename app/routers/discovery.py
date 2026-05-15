"""
Discovery router for guest-friendly area exploration and provider browsing
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional

from app.database import get_db
from app.services.area_intelligence_service import AreaIntelligenceService
from app.schemas.discovery import (
    AreaSummaryResponse,
    TrendingCategoryResponse,
    ProviderProfileResponse,
    BrowseByCategoryResponse
)
from app.models.category import Category

router = APIRouter(prefix="/discovery", tags=["Discovery"])


@router.get("/area-summary", response_model=AreaSummaryResponse)
async def get_area_summary(
    latitude: float = Query(..., description="Center point latitude"),
    longitude: float = Query(..., description="Center point longitude"),
    radius_km: int = Query(10, ge=1, le=50, description="Search radius in kilometers"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive area summary including trending categories, statistics, and demand signals.
    
    This endpoint is guest-accessible (no authentication required).
    
    Example: GET /discovery/area-summary?latitude=6.5244&longitude=3.3792&radius_km=10
    """
    try:
        area_service = AreaIntelligenceService(db)
        summary = await area_service.get_area_summary(latitude, longitude, radius_km)
        return summary
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch area summary: {str(e)}"
        )


@router.get("/trending-categories", response_model=List[TrendingCategoryResponse])
async def get_trending_categories(
    latitude: float = Query(..., description="Center point latitude"),
    longitude: float = Query(..., description="Center point longitude"),
    radius_km: int = Query(10, ge=1, le=50, description="Search radius in kilometers"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get trending service categories ranked by demand (job count + service availability).
    
    This endpoint is guest-accessible (no authentication required).
    
    Example: GET /discovery/trending-categories?latitude=6.5244&longitude=3.3792&radius_km=10&limit=10
    """
    try:
        area_service = AreaIntelligenceService(db)
        categories = await area_service.get_trending_categories(
            latitude, longitude, radius_km, limit
        )
        return categories
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch trending categories: {str(e)}"
        )


@router.get("/browse-by-category", response_model=BrowseByCategoryResponse)
async def browse_providers_by_category(
    category_id: int = Query(..., description="Category ID to filter by"),
    latitude: float = Query(..., description="Center point latitude"),
    longitude: float = Query(..., description="Center point longitude"),
    radius_km: int = Query(10, ge=1, le=50, description="Search radius in kilometers"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    rating_min: Optional[float] = Query(None, ge=0, le=5, description="Minimum rating filter"),
    db: AsyncSession = Depends(get_db)
):
    """
    Browse service providers by category in a specific area.
    
    This endpoint is guest-accessible (no authentication required).
    
    Example: GET /discovery/browse-by-category?category_id=1&latitude=6.5244&longitude=3.3792&radius_km=10
    """
    try:
        # Verify category exists
        cat_query = select(Category).where(Category.id == category_id)
        cat_result = await db.execute(cat_query)
        category = cat_result.scalar_one_or_none()
        
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category {category_id} not found"
            )
        
        area_service = AreaIntelligenceService(db)
        providers = await area_service.get_top_providers_by_category(
            category_id, latitude, longitude, radius_km, limit
        )
        
        # Apply rating filter if specified
        if rating_min:
            providers = [p for p in providers if p["rating"] >= rating_min]
        
        return BrowseByCategoryResponse(
            category_id=category_id,
            category_name=category.name,
            providers=[ProviderProfileResponse(**p) for p in providers],
            total_count=len(providers)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to browse providers: {str(e)}"
        )


@router.get("/providers/{provider_id}", response_model=dict)
async def get_provider_profile(
    provider_id: int = Path(..., description="Provider/Service ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed provider profile including portfolio and reviews.
    
    This endpoint is guest-accessible (no authentication required).
    Works with both service IDs and worker IDs.
    
    Example: GET /discovery/providers/123
    """
    from app.models.service import Service
    from app.models.user import User
    from app.models.review import Review
    
    try:
        # Try to get as a service first
        service_query = select(Service).where(Service.id == provider_id)
        service_result = await db.execute(service_query)
        service = service_result.scalar_one_or_none()
        
        if service:
            worker = service.worker
            
            # Get reviews
            reviews_query = select(Review).where(Review.service_id == provider_id)
            reviews_result = await db.execute(reviews_query)
            reviews = reviews_result.scalars().all()
            
            # Calculate rating
            ratings = [r.rating for r in reviews if r.rating]
            avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
            
            # Get certifications
            certifications = []
            if hasattr(worker, 'certifications') and worker.certifications:
                certifications = worker.certifications
            
            # Get portfolio (if stored in metadata)
            portfolio = []
            if hasattr(service, 'portfolio_items') and service.portfolio_items:
                portfolio = service.portfolio_items
            
            return {
                "id": provider_id,
                "type": "service_provider",
                "name": f"{worker.first_name or ''} {worker.last_name or ''}".strip(),
                "avatar_url": worker.avatar_url,
                "title": service.name,
                "description": service.description,
                "rating": round(avg_rating, 1),
                "review_count": len(reviews),
                "certifications": certifications,
                "portfolio": portfolio,
                "price": float(service.price) if service.price else 0,
                "pricing_model": service.pricing_model,
                "is_verified": worker.is_kyc_verified,
                "reviews": [
                    {
                        "id": r.id,
                        "rating": r.rating,
                        "comment": r.comment,
                        "created_at": r.created_at.isoformat() if r.created_at else None
                    }
                    for r in reviews
                ],
                "city": service.city,
                "country": service.country,
                "messaging_enabled": False  # Disabled for guest users
            }
        
        # Try to get as a worker
        worker_query = select(User).where(User.id == provider_id)
        worker_result = await db.execute(worker_query)
        worker = worker_result.scalar_one_or_none()
        
        if worker:
            # Get all services by this worker
            services_query = select(Service).where(Service.worker_id == provider_id)
            services_result = await db.execute(services_query)
            services = services_result.scalars().all()
            
            # Get combined rating across all services
            if services:
                reviews_query = select(Review).where(
                    Review.service_id.in_([s.id for s in services])
                )
                reviews_result = await db.execute(reviews_query)
                reviews = reviews_result.scalars().all()
                ratings = [r.rating for r in reviews if r.rating]
                avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
            else:
                avg_rating = 0.0
                reviews = []
            
            return {
                "id": provider_id,
                "type": "worker",
                "name": f"{worker.first_name or ''} {worker.last_name or ''}".strip(),
                "avatar_url": worker.avatar_url,
                "reputation_score": float(worker.reputation_score or 0.0),
                "rating": round(avg_rating, 1),
                "review_count": len(reviews),
                "is_verified": worker.is_kyc_verified,
                "services": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "description": s.description,
                        "price": float(s.price) if s.price else 0,
                        "pricing_model": s.pricing_model
                    }
                    for s in services
                ],
                "messaging_enabled": False  # Disabled for guest users
            }
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch provider profile: {str(e)}"
        )
