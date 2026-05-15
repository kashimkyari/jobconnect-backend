from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.models.user import User, UserRole
from app.schemas.user import UserProfile
from app.database import get_db
from app.utils.security import get_current_user, check_permissions
from app.models.worker_profile import UserService
from app.models.review import Review
from app.models.service import Service
from app.models.file import File

router = APIRouter(prefix="/workers", tags=["Workers"])


@router.get("/search", response_model=List[UserProfile])
async def search_workers(
    q: Optional[str] = Query(None, description="Search query for name, skills, or service category"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    category: Optional[str] = Query(None, description="Filter by service category"),
    skill: Optional[str] = Query(None, description="Filter by skill"),
    location: Optional[str] = Query(None, description="Filter by location (text-based)"),
    latitude: Optional[float] = Query(None, description="Employer's latitude for location-based filtering"),
    longitude: Optional[float] = Query(None, description="Employer's longitude for location-based filtering"),
    radius_km: Optional[int] = Query(None, ge=1, le=500, description="Search radius in kilometers (defaults to your search radius)"),
    experience_level: Optional[str] = Query(None, description="Filter by experience level"),
    min_rating: Optional[float] = Query(None, ge=0, le=5, description="Minimum average rating"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER, UserRole.ADMIN))
):
    """
    Search and filter workers for employers to browse and hire.
    Supports filtering by services, skills, location, experience level, and rating.
    
    For location-based filtering, provide latitude and longitude parameters.
    For text-based location search, use the location parameter.
    """
    # If latitude and longitude provided, use geospatial filtering
    if latitude is not None and longitude is not None:
        from app.services.location_service import LocationService
        location_service = LocationService(db)
        radius_km = location_service.resolve_search_radius_km(user=current_user, radius_km=radius_km)
        
        # Get nearby workers
        nearby_workers = await location_service.get_nearby_workers_with_distance(
            employer_latitude=latitude,
            employer_longitude=longitude,
            radius_km=radius_km,
            service_category=category,
            experience_level=experience_level,
            min_rating=min_rating or 0.0,
            limit=limit + skip  # Get extra for filtering/pagination
        )
        
        # Apply additional text-based filters if provided
        filtered_workers = []
        for worker_data in nearby_workers:
            worker = worker_data["worker"]
            
            # Apply text filters
            if q:
                search_term = q.lower()
                if not (
                    (worker.first_name and search_term in worker.first_name.lower()) or
                    (worker.last_name and search_term in worker.last_name.lower()) or
                    (worker.about_me and search_term in worker.about_me.lower()) or
                    (worker.service_category and search_term in worker.service_category.lower())
                ):
                    continue
            
            if skill and worker.skills and skill not in worker.skills:
                continue
            
            filtered_workers.append(worker_data)
        
        # Apply skip and limit
        filtered_workers = filtered_workers[skip:skip+limit]
        
        # Build rating + review count maps for this slice
        worker_ids = [w["worker"].id for w in filtered_workers if w.get("worker")]
        review_map = {}
        service_price_map = {}
        if worker_ids:
            review_stats = await db.execute(
                select(
                    Review.reviewee_id,
                    func.avg(Review.rating).label("avg_rating"),
                    func.count(Review.id).label("review_count")
                )
                .where(Review.reviewee_id.in_(worker_ids))
                .group_by(Review.reviewee_id)
            )
            review_map = {
                row.reviewee_id: {
                    "avg_rating": float(row.avg_rating or 0),
                    "review_count": int(row.review_count or 0),
                }
                for row in review_stats
            }

            service_stats = await db.execute(
                select(
                    Service.worker_id,
                    func.avg(Service.price).label("avg_price")
                )
                .where(Service.worker_id.in_(worker_ids))
                .group_by(Service.worker_id)
            )
            service_price_map = {
                row.worker_id: float(row.avg_price or 0)
                for row in service_stats
            }

        # Build profiles with distance info
        worker_profiles = []
        for worker_data in filtered_workers:
            worker = worker_data["worker"]
            review_stats = review_map.get(worker.id, {})
            avg_rating = review_stats.get("avg_rating", 0.0)
            review_count = review_stats.get("review_count", 0)
            avg_service_price = service_price_map.get(worker.id, 0.0)
            profile_data = {
                **worker.__dict__,
                "avg_rating": avg_rating,
                "average_rating": avg_rating,
                "reputation_score": worker.reputation_score or 0.0,
                "total_reviews": review_count,
                "average_service_price": avg_service_price,
                "total_jobs_posted": 0,
                "total_jobs_completed": 0,
                "profile_completion_percentage": 0,
                "subscription": None,
                "recent_transactions": [],
                "distance_km": worker_data["distance_km"],
                "distance_display": worker_data["distance_display"]
            }
            if hasattr(worker, 'skills') and worker.skills:
                profile_data['skills'] = worker.skills if isinstance(worker.skills, list) else list(worker.skills)
            else:
                profile_data['skills'] = []
            
            profile = UserProfile(**profile_data)
            worker_profiles.append(profile)
        
        return worker_profiles
    
    # Fallback to original text-based search
    query = (
        select(User)
        .where(User.role == UserRole.WORKER)
        .where(User.is_active == True)
        .options(
            selectinload(User.services_offered),
            selectinload(User.services),
            selectinload(User.recent_works),
            selectinload(User.jobs_worked)
        )
    )

    # Apply filters
    if q:
        search_term = f"%{q.lower()}%"
        query = query.where(
            or_(
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.about_me.ilike(search_term),
                User.service_category.ilike(search_term),
                User.skills.contains([q])  # JSONB contains for skills
            )
        )

    if service:
        # Filter by service name in services_offered
        query = query.join(UserService).where(
            UserService.service_name.ilike(f"%{service}%")
        )

    if category:
        query = query.where(User.service_category.ilike(f"%{category}%"))

    if skill:
        # Filter by skill in skills JSONB array
        query = query.where(User.skills.contains([skill]))

    if location:
        query = query.where(User.location.ilike(f"%{location}%"))

    if experience_level:
        query = query.where(User.experience_level == experience_level)

    # Apply pagination
    query = query.offset(skip).limit(limit)

    # Subquery to calculate average rating + review count
    rating_subquery = (
        select(
            Review.reviewee_id,
            func.avg(Review.rating).label("avg_rating"),
            func.count(Review.id).label("review_count"),
        )
        .group_by(Review.reviewee_id)
        .subquery()
    )

    # Subquery to calculate average service price
    service_price_subquery = (
        select(
            Service.worker_id,
            func.avg(Service.price).label("avg_price")
        )
        .group_by(Service.worker_id)
        .subquery()
    )

    # Join with the subquery
    query = query.outerjoin(rating_subquery, User.id == rating_subquery.c.reviewee_id)
    query = query.outerjoin(service_price_subquery, User.id == service_price_subquery.c.worker_id)

    # Add average rating to the selection
    query = query.add_columns(
        rating_subquery.c.avg_rating,
        rating_subquery.c.review_count,
        service_price_subquery.c.avg_price
    )

    # Filter by min_rating if specified
    if min_rating:
        query = query.where(rating_subquery.c.avg_rating >= min_rating)

    result = await db.execute(query)
    workers_with_ratings = result.all()

    # Build profiles
    worker_profiles = []
    for worker, avg_rating, review_count, avg_price in workers_with_ratings:
        profile_data = {
            **worker.__dict__,
            "avg_rating": avg_rating or 0.0,
            "average_rating": avg_rating or 0.0,
            "reputation_score": worker.reputation_score or 0.0,
            "total_reviews": int(review_count or 0),
            "average_service_price": float(avg_price or 0.0),
            "total_jobs_posted": 0,
            "total_jobs_completed": len([j for j in worker.jobs_worked if j.status.value == "completed"]),
            "profile_completion_percentage": 0,
            "subscription": None,
            "recent_transactions": [],
        }
        if hasattr(worker, 'skills') and worker.skills:
            profile_data['skills'] = worker.skills if isinstance(worker.skills, list) else list(worker.skills)
        else:
            profile_data['skills'] = []
        
        profile = UserProfile(**profile_data)
        worker_profiles.append(profile)

    return worker_profiles


@router.get("/{worker_id}", response_model=UserProfile)
async def get_worker_profile(
    worker_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER, UserRole.ADMIN))
):
    """
    Get detailed profile of a specific worker for employers to review before hiring.
    """
    query = (
        select(User)
        .where(User.id == worker_id)
        .where(User.role == UserRole.WORKER)
        .options(
            selectinload(User.services_offered),
            selectinload(User.services).selectinload(Service.category),  # Load new Service model services
            selectinload(User.recent_works),
            selectinload(User.reviews_received),
            selectinload(User.jobs_worked)
        )
    )
    result = await db.execute(query)
    worker = result.scalar_one_or_none()

    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worker not found"
        )

    # Get average rating
    rating_query = select(func.avg(Review.rating)).where(Review.reviewee_id == worker.id)
    rating_result = await db.execute(rating_query)
    avg_rating = rating_result.scalar() or 0.0

    # Build profile
    profile_data = {
        **worker.__dict__,
        "average_rating": avg_rating,
        "total_jobs_posted": 0,
        "total_jobs_completed": len([j for j in worker.jobs_worked if j.status.value == "completed"]),
        "profile_completion_percentage": 0,
        "subscription": None,
        "recent_transactions": [],
    }
    if hasattr(worker, 'skills') and worker.skills:
        profile_data['skills'] = worker.skills if isinstance(worker.skills, list) else list(worker.skills)
    else:
        profile_data['skills'] = []

    # Merge detailed Service model services into services_offered for richer worker profile display.
    if hasattr(worker, 'services') and worker.services:
        existing_services = profile_data.get('services_offered', []) or []

        service_ids = [svc.id for svc in worker.services]

        image_map = {}
        if service_ids:
            file_result = await db.execute(
                select(File.reference_id, File.file_path)
                .where(
                    File.reference_type == "service",
                    File.reference_id.in_(service_ids),
                )
                .order_by(File.id.asc())
            )
            for reference_id, file_path in file_result.all():
                if reference_id not in image_map:
                    image_map[reference_id] = file_path

        ratings_map = {}
        if service_ids:
            ratings_result = await db.execute(
                select(
                    Review.service_id,
                    func.count(Review.id).label("total_reviews"),
                    func.avg(Review.rating).label("average_rating"),
                )
                .where(
                    Review.service_id.in_(service_ids),
                    Review.reviewee_id == worker.id,
                )
                .group_by(Review.service_id)
            )
            for service_id, total_reviews, average_rating in ratings_result.all():
                ratings_map[service_id] = {
                    "total_reviews": int(total_reviews or 0),
                    "average_rating": float(average_rating or 0.0),
                }

        new_services = [
            {
                'id': svc.id,
                'user_id': svc.worker_id,
                'service_id': svc.id,
                'service_name': svc.name,  # Map Service.name to service_name
                'description': svc.description,
                'price': float(svc.price) if svc.price is not None else None,
                'pricing_model': svc.pricing_model,
                'estimated_delivery_time': svc.estimated_delivery_time,
                'revisions': svc.revisions,
                'tags': svc.tags or [],
                'category_id': svc.category_id,
                'category_name': svc.category.name if getattr(svc, "category", None) else None,
                'city': svc.city,
                'country': svc.country,
                'image_url': image_map.get(svc.id),
                'total_reviews': ratings_map.get(svc.id, {}).get("total_reviews", 0),
                'average_rating': ratings_map.get(svc.id, {}).get("average_rating", 0.0),
                'created_at': svc.created_at.isoformat() if svc.created_at else None,
                'updated_at': svc.updated_at.isoformat() if svc.updated_at else None,
            }
            for svc in worker.services
        ]
        profile_data['services_offered'] = existing_services + new_services

    profile = UserProfile(**profile_data)

    return profile


@router.get("/", response_model=List[UserProfile])
async def list_workers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER, UserRole.ADMIN))
):
    """
    List all active workers for employers to browse.
    """
    query = (
        select(User)
        .where(User.role == UserRole.WORKER)
        .where(User.is_active == True)
        .options(
            selectinload(User.services_offered),
            selectinload(User.recent_works),
            selectinload(User.jobs_worked)
        )
        .offset(skip)
        .limit(limit)
    )
    # Subquery to calculate average rating
    rating_subquery = (
        select(Review.reviewee_id, func.avg(Review.rating).label("avg_rating"))
        .group_by(Review.reviewee_id)
        .subquery()
    )

    # Join with the subquery
    query = query.outerjoin(rating_subquery, User.id == rating_subquery.c.reviewee_id)

    # Add average rating to the selection
    query = query.add_columns(rating_subquery.c.avg_rating)

    result = await db.execute(query)
    workers_with_ratings = result.all()

    # Build profiles
    worker_profiles = []
    for worker, avg_rating in workers_with_ratings:
        profile_data = {
            **worker.__dict__,
            "average_rating": avg_rating or 0.0,
            "total_jobs_posted": 0,
            "total_jobs_completed": len([j for j in worker.jobs_worked if j.status.value == "completed"]),
            "profile_completion_percentage": 0,
            "subscription": None,
            "recent_transactions": [],
        }
        if hasattr(worker, 'skills') and worker.skills:
            profile_data['skills'] = worker.skills if isinstance(worker.skills, list) else list(worker.skills)
        else:
            profile_data['skills'] = []
        
        profile = UserProfile(**profile_data)
        worker_profiles.append(profile)

    return worker_profiles


@router.get("/nearby/list", response_model=List[dict])
async def get_nearby_workers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_permissions(UserRole.EMPLOYER, UserRole.ADMIN)),
    latitude: float = None,
    longitude: float = None,
    radius_km: int = None,
    service_category: str = None,
    experience_level: str = None,
    min_rating: float = 0.0,
    limit: int = 50,
):
    """Get workers nearby the employer's location.
    
    Query parameters:
    - latitude: Employer's latitude (uses current employer's location if not provided)
    - longitude: Employer's longitude (uses current employer's location if not provided)
    - radius_km: Search radius in kilometers (uses employer's preference if not provided)
    - service_category: Optional service category filter
    - experience_level: Optional experience level filter
    - min_rating: Minimum reputation score (default 0.0)
    - limit: Maximum results (default 50)
    """
    from app.services.location_service import LocationService
    from app.services.worker_matching_service import WorkerMatchingService
    
    # Use provided location or fall back to employer's stored location
    if latitude is None or longitude is None:
        if current_user.latitude is None or current_user.longitude is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location not provided and employer location not set. Please provide latitude and longitude."
            )
        latitude = current_user.latitude
        longitude = current_user.longitude
    
    location_service = LocationService(db)
    radius_km = location_service.resolve_search_radius_km(user=current_user, radius_km=radius_km)
    nearby_workers = await location_service.get_nearby_workers(
        employer_latitude=latitude,
        employer_longitude=longitude,
        radius_km=radius_km,
        service_category=service_category,
        experience_level=experience_level,
        min_rating=min_rating,
        limit=limit
    )
    
    # Convert to response format with distance
    result = []
    for worker, distance in nearby_workers:
        worker_data = {
            "id": worker.id,
            "first_name": worker.first_name,
            "last_name": worker.last_name,
            "avatar_url": worker.avatar_url,
            "headline": worker.headline,
            "service_category": worker.service_category,
            "experience_level": worker.experience_level,
            "reputation_score": worker.reputation_score,
            "skills": worker.skills or [],
            "distance_km": round(distance, 2),
            "latitude": worker.latitude,
            "longitude": worker.longitude,
            "city": worker.city,
            "country": worker.country,
        }
        result.append(worker_data)
    
    return result
