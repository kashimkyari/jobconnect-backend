from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from typing import List, Optional, Union

from app.database import get_db
from app.services import employer_dashboard_service
from app.schemas.worker_profile import ServiceShowcaseItem
from app.schemas.service import ServiceCreate, ServiceInDB, ServiceUpdate, ServiceDetailResponse
from app.schemas.category import CategoryInDB
from app.schemas.booking import BookingListResponse, BookingResponse
from pydantic import BaseModel
from app.models.user import User, UserRole
from app.models.service import Service
from app.models.category import Category
from app.models.file import File
from app.models.review import Review
from app.models.booking import Booking
from ..services.auth_service import get_current_user
from app.models.enums import BookingStatus

# Mapping of frontend category IDs to database category names
# These match the APP_CATEGORIES in the mobile app (src/config/categories.js)
FRONTEND_TO_DB_CATEGORIES = {
    "healthcare": "Healthcare",
    "cleaning": "Cleaning",
    "tutoring": "Tutoring",
    "logistics": "Logistics",
    "web-development": "Web Development",
    "graphic-design": "Graphic Design",
    "writing-content": "Writing & Content",
    "photography": "Photography",
    "plumbing-handyman": "Plumbing & Handyman",
    "consulting": "Consulting",
    "marketing": "Marketing",
    "video-production": "Video Production",
    "pet-care": "Pet Care",
    "fitness-training": "Fitness & Training",
    "event-planning": "Event Planning",
}

# Backward-compatible aliases for environments with older/newer seed data.
FRONTEND_TO_DB_CATEGORY_ALIASES = {
    "tutoring": ["Tutoring", "Tutoring & Education"],
    "logistics": ["Logistics", "Logistics & Delivery"],
    "marketing": ["Marketing", "Marketing & Advertising"],
}


def _normalize_category_token(value: str) -> str:
    """Normalize category strings/ids to a comparable token."""
    if not value:
        return ""
    normalized = value.strip().lower()
    normalized = normalized.replace("&", " and ")
    for ch in ["/", "_", "(", ")", ",", "."]:
        normalized = normalized.replace(ch, " ")
    normalized = normalized.replace("-", " ")
    return " ".join(normalized.split())


async def _resolve_category(db: AsyncSession, category_value: Union[str, int]) -> Optional[Category]:
    """Resolve category by integer id, frontend slug, or category name aliases."""
    if isinstance(category_value, int):
        result = await db.execute(select(Category).filter(Category.id == category_value))
        return result.scalars().first()

    raw_value = str(category_value).strip()
    if not raw_value:
        return None

    # Support numeric strings.
    if raw_value.isdigit():
        result = await db.execute(select(Category).filter(Category.id == int(raw_value)))
        return result.scalars().first()

    raw_key = raw_value.lower()
    candidates = [raw_value]

    mapped_name = FRONTEND_TO_DB_CATEGORIES.get(raw_key)
    if mapped_name:
        candidates.append(mapped_name)
    candidates.extend(FRONTEND_TO_DB_CATEGORY_ALIASES.get(raw_key, []))

    normalized_target_tokens = {_normalize_category_token(item) for item in candidates if item}
    normalized_target_tokens.add(_normalize_category_token(raw_key))

    result = await db.execute(select(Category))
    categories = result.scalars().all()
    for category in categories:
        normalized_name = _normalize_category_token(category.name)
        if normalized_name in normalized_target_tokens:
            return category

    # Last fallback: case-insensitive contains match for unusual category names.
    result = await db.execute(select(Category).filter(Category.name.ilike(f"%{raw_value}%")))
    return result.scalars().first()

router = APIRouter()


def extract_request_id(request: Request) -> Optional[str]:
    return (
        request.headers.get("X-Request-ID")
        or request.headers.get("Idempotency-Key")
        or request.headers.get("X-Idempotency-Key")
    )


def _normalize_duplicate_value(value) -> str:
    if hasattr(value, "value"):
        value = value.value
    return " ".join(str(value or "").strip().lower().split())


def _normalize_price(value) -> Optional[str]:
    if value is None:
        return None
    return f"{float(value):.2f}"


async def _find_existing_service_by_request_id(
    db: AsyncSession,
    worker_id: int,
    request_id: Optional[str],
) -> Optional[Service]:
    if not request_id:
        return None

    result = await db.execute(
        select(Service)
        .where(
            Service.worker_id == worker_id,
            Service.last_request_id == request_id,
        )
        .order_by(Service.created_at.desc())
    )
    return result.scalars().first()


async def _find_duplicate_service(
    db: AsyncSession,
    worker_id: int,
    category_id: int,
    service: ServiceCreate,
) -> Optional[Service]:
    result = await db.execute(
        select(Service)
        .where(
            Service.worker_id == worker_id,
            Service.category_id == category_id,
        )
        .order_by(Service.created_at.desc())
        .limit(25)
    )
    existing_services = result.scalars().all()

    normalized_name = _normalize_duplicate_value(service.name)
    normalized_description = _normalize_duplicate_value(service.description)
    normalized_city = _normalize_duplicate_value(service.city)
    normalized_country = _normalize_duplicate_value(service.country or "Nigeria")
    normalized_pricing_model = _normalize_duplicate_value(service.pricing_model)
    normalized_price = _normalize_price(service.price)

    for existing in existing_services:
        if _normalize_duplicate_value(existing.name) != normalized_name:
            continue
        if _normalize_duplicate_value(existing.description) != normalized_description:
            continue
        if _normalize_duplicate_value(existing.city) != normalized_city:
            continue
        if _normalize_duplicate_value(existing.country) != normalized_country:
            continue
        if _normalize_duplicate_value(existing.pricing_model) != normalized_pricing_model:
            continue
        if _normalize_price(existing.price) != normalized_price:
            continue
        return existing

    return None

class ServiceWithCategoriesResponse(BaseModel):
    service: ServiceInDB
    categories: List[CategoryInDB]

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_service(
    request: Request,
    service: ServiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new service for the logged-in worker.
    """
    if current_user.role != "worker":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workers can create services.",
        )

    # Handle category lookup by frontend slug/name or integer id.
    category_input = service.category_id
    category = await _resolve_category(db, category_input)
    if not category:
        valid_categories = ", ".join(FRONTEND_TO_DB_CATEGORIES.keys())
        if isinstance(category_input, int) or (isinstance(category_input, str) and category_input.isdigit()):
            detail = f"Category with id {category_input} does not exist."
        else:
            detail = f"Category '{category_input}' does not exist. Valid categories: {valid_categories}"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )
    category_id = category.id
    request_id = extract_request_id(request)

    existing_request_service = await _find_existing_service_by_request_id(db, current_user.id, request_id)
    if existing_request_service:
        return {
            "id": existing_request_service.id,
            "name": existing_request_service.name,
            "description": existing_request_service.description,
            "price": existing_request_service.price,
            "pricing_model": existing_request_service.pricing_model,
            "estimated_delivery_time": existing_request_service.estimated_delivery_time,
            "revisions": existing_request_service.revisions,
            "tags": existing_request_service.tags or [],
            "city": existing_request_service.city,
            "country": existing_request_service.country or "Nigeria",
            "latitude": existing_request_service.latitude,
            "longitude": existing_request_service.longitude,
            "worker_id": existing_request_service.worker_id,
            "category_id": existing_request_service.category_id,
            "category_name": category.name,
        }

    duplicate_service = await _find_duplicate_service(db, current_user.id, category_id, service)
    if duplicate_service:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A similar service already exists. Edit the existing service instead of creating another one.",
        )

    service_data = service.dict()
    image_ids = service_data.pop("image_ids", [])
    
    # Create service - ensure enum is converted to string value
    pricing_model_value = (
        service.pricing_model.value
        if hasattr(service.pricing_model, "value")
        else str(service.pricing_model)
    )
    
    db_service = Service(
        name=service.name,
        description=service.description,
        price=service.price,
        pricing_model=pricing_model_value,
        estimated_delivery_time=service.estimated_delivery_time,
        revisions=service.revisions,
        tags=service.tags or [],
        city=service.city,
        country=service.country or "Nigeria",
        latitude=service.latitude,
        longitude=service.longitude,
        category_id=category_id,
        worker_id=current_user.id,
        last_request_id=request_id,
        last_request_at=datetime.utcnow() if request_id else None,
    )
    db.add(db_service)
    
    try:
        await db.flush()
        service_id = db_service.id
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        print(f"[DEBUG] IntegrityError: {error_msg}")
        print(f"[DEBUG] Service: name={db_service.name}, category_id={db_service.category_id}, worker_id={db_service.worker_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create service. Error: {error_msg[:100]}",
        )

    # Handle image associations
    if image_ids:
        for image_id in image_ids:
            result = await db.execute(select(File).filter(File.id == image_id))
            image_file = result.scalars().first()
            if not image_file or image_file.user_id != current_user.id:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid image_id: {image_id}",
                )
            
            image_file.reference_id = service_id
            image_file.reference_type = "service"
            db.add(image_file)

    # Commit
    await db.commit()

    # Return simple response
    return {
        "id": service_id,
        "name": service.name,
        "description": service.description,
        "price": service.price,
        "pricing_model": service.pricing_model,
        "estimated_delivery_time": service.estimated_delivery_time,
        "revisions": service.revisions,
        "tags": service.tags or [],
        "city": service.city,
        "country": service.country or "Nigeria",
        "latitude": service.latitude,
        "longitude": service.longitude,
        "worker_id": current_user.id,
        "category_id": category_id,
        "category_name": category.name,
    }

@router.get("/categories", response_model=List[CategoryInDB])
async def get_categories(db: AsyncSession = Depends(get_db)):
    """
    Get all service categories.
    """
    result = await db.execute(select(Category))
    categories = result.scalars().all()
    return categories

@router.get("/me", response_model=List[ServiceInDB])
async def get_my_services(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all services for the logged-in worker.
    Includes image data for each service.
    Returns relative file paths - client handles URL building via buildFullAssetUrl.
    """
    if current_user.role != "worker":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workers can view their services.",
        )
    
    try:
        print(f"\n📡 [Backend] GET /services/me endpoint called for user {current_user.id}")
        
        # Fetch services
        result = await db.execute(select(Service).filter(Service.worker_id == current_user.id))
        services = result.scalars().all()
        
        print(f"   - Found {len(services)} services")
        
        # For each service, fetch associated images and category
        service_ids = [service.id for service in services]
        booking_counts = {}
        if service_ids:
            booking_result = await db.execute(
                select(Booking.service_id, func.count(Booking.id))
                .where(Booking.service_id.in_(service_ids))
                .group_by(Booking.service_id)
            )
            booking_counts = {row[0]: int(row[1]) for row in booking_result.all()}

        services_with_images = []
        for service in services:
            # Fetch category name
            category_result = await db.execute(
                select(Category).filter(Category.id == service.category_id)
            )
            category = category_result.scalars().first()
            category_name = category.name if category else None
            
            # Fetch images for this service
            image_result = await db.execute(
                select(File).filter(
                    (File.reference_id == service.id) & 
                    (File.reference_type == "service")
                )
            )
            images = image_result.scalars().all()
            
            # Set primary image (first image or None) - return relative path
            image_url = None
            if images:
                image_url = images[0].file_path
            
            # Transform service to dict and add image data - return relative paths
            service_dict = {
                "id": service.id,
                "name": service.name,
                "description": service.description,
                "price": service.price,
                "pricing_model": service.pricing_model,
                "estimated_delivery_time": service.estimated_delivery_time,
                "revisions": service.revisions,
                "tags": service.tags or [],
                "city": service.city,
                "country": service.country or "Nigeria",
                "latitude": service.latitude,
                "longitude": service.longitude,
                "worker_id": service.worker_id,
                "category_id": service.category_id,
                "category_name": category_name,
                "image_url": image_url,
                "images": [
                    {
                        "id": img.id,
                        "file_path": img.file_path,  # Return relative path
                        "original_filename": img.original_filename,
                    }
                    for img in images
                ],
                "total_orders": booking_counts.get(service.id, 0),
            }
            services_with_images.append(service_dict)
            print(f"   - Service: {service.name}, category: {category_name}, images: {len(images)}, primary: {image_url}")
        
        print(f"✅ [Backend] Returning {len(services_with_images)} services with relative image paths")
        return services_with_images
    except Exception as e:
        print(f"❌ [Backend] Error in GET /services/me: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching services: {str(e)}"
        )

@router.get("/featured", response_model=List[ServiceShowcaseItem])
async def get_featured_services(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 10,
):
    """
    Get a list of recommended worker services for the employer home screen.
    Returns Services from workers (not recent works).
    Excludes services posted by the current user.
    [Deprecated: use /recommended instead]
    """
    try:
        print(f"\n📡 [Backend] GET /services/featured endpoint called")
        print(f"   - Current user: {current_user.id} ({current_user.first_name} {current_user.last_name})")
        print(f"   - User role: {current_user.role}")
        print(f"   - Requested limit: {limit}")
        
        featured_services = await employer_dashboard_service.get_featured_services(
            db, limit=limit, exclude_user_id=current_user.id
        )
        
        print(f"✅ [Backend] Returning {len(featured_services)} featured services")
        for idx, service in enumerate(featured_services):
            print(f"   [{idx + 1}] {service.name} by {service.worker.first_name} {service.worker.last_name} - ₦{service.price} ({service.pricing_model})")
        
        return featured_services
    except Exception as e:
        print(f"❌ [Backend] Error in GET /services/featured: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recommended", response_model=List[ServiceShowcaseItem])
async def get_recommended_services(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 10,
):
    """
    Get a list of recommended worker services for the employer home screen.
    These are curated services from workers, randomly selected from recent listings.
    Excludes services posted by the current user.
    """
    try:
        print(f"\n📡 [Backend] GET /services/recommended endpoint called")
        print(f"   - Current user: {current_user.id} ({current_user.first_name} {current_user.last_name})")
        print(f"   - Requested limit: {limit}")
        
        recommended_services = await employer_dashboard_service.get_featured_services(
            db, limit=limit, exclude_user_id=current_user.id
        )
        
        print(f"✅ [Backend] Returning {len(recommended_services)} recommended services")
        for idx, service in enumerate(recommended_services):
            print(f"   [{idx + 1}] {service.name} by {service.worker.first_name} {service.worker.last_name} - ₦{service.price}")
        
        return recommended_services
    except Exception as e:
        print(f"❌ [Backend] Error in GET /services/recommended: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{service_id}", response_model=dict)
async def get_service_detail(
    service_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed information about a specific service.
    Includes complete worker profile and all service details for employers.
    """
    result = await db.execute(
        select(Service).filter(Service.id == service_id)
    )
    service = result.scalars().first()
    
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found."
        )
    
    # Fetch worker details
    worker_result = await db.execute(
        select(User).filter(User.id == service.worker_id)
    )
    worker = worker_result.scalars().first()
    
    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worker not found."
        )
    
    # Fetch service images
    images_result = await db.execute(
        select(File).filter(
            File.reference_id == service_id,
            File.reference_type == "service"
        )
    )
    images = images_result.scalars().all()
    
    # Fetch category info
    category_result = await db.execute(
        select(Category).filter(Category.id == service.category_id)
    )
    category = category_result.scalars().first()
    
    # Calculate total reviews for the worker
    from sqlalchemy import func
    from app.models.review import Review
    total_reviews_result = await db.execute(
        select(func.count(Review.id)).where(
            Review.reviewee_id == worker.id
        )
    )
    total_reviews = total_reviews_result.scalar() or 0

    # Fetch service-specific reviews (reviews written about this worker for this service)
    service_reviews_result = await db.execute(
        select(Review)
        .where(
            Review.service_id == service.id,
            Review.reviewee_id == worker.id,
        )
        .options(selectinload(Review.reviewer))
        .order_by(Review.created_at.desc())
        .limit(50)
    )
    service_reviews = service_reviews_result.scalars().all()

    service_review_stats_result = await db.execute(
        select(func.count(Review.id), func.avg(Review.rating)).where(
            Review.service_id == service.id,
            Review.reviewee_id == worker.id,
        )
    )
    service_total_reviews, service_average_rating = service_review_stats_result.first()
    service_total_reviews = int(service_total_reviews or 0)
    service_average_rating = float(service_average_rating or 0.0)
    
    # Build response with complete details
    return {
        # Service Details
        "id": service.id,
        "name": service.name,
        "description": service.description,
        "price": float(service.price),
        "pricing_model": service.pricing_model,
        "estimated_delivery_time": service.estimated_delivery_time,
        "revisions": service.revisions,
        "tags": service.tags or [],
        "city": service.city,
        "country": service.country or "Nigeria",
        "category_id": service.category_id,
        "category_name": category.name if category else None,
        "worker_id": service.worker_id,
        
        # Images
        "image_url": images[0].file_path if images else None,
        "images": [
            {
                "id": img.id,
                "file_path": img.file_path,
                "updated_at": img.updated_at.isoformat() if hasattr(img, 'updated_at') and img.updated_at else None
            }
            for img in images
        ],
        
        # Comprehensive Worker Details
        "worker": {
            "id": worker.id,
            "first_name": worker.first_name,
            "last_name": worker.last_name,
            "email": worker.email,
            "avatar_url": worker.avatar_url,
            "headline": getattr(worker, 'headline', None),
            "bio": getattr(worker, 'about_me', None) or "",
            "rating": float(worker.reputation_score) if worker.reputation_score else 0.0,
            "total_reviews": int(total_reviews),
            "total_jobs": getattr(worker, 'total_jobs', 0) or 0,
            "on_time_rate": float(getattr(worker, 'on_time_rate', 0) or 0),
            "response_time": getattr(worker, 'response_time', None),
            "is_verified": getattr(worker, 'is_email_verified', False),
            "is_email_verified": getattr(worker, 'is_email_verified', False),
            "badges": getattr(worker, 'badges', []) or [],
            "skills": getattr(worker, 'skills', []) or [],
            "languages": getattr(worker, 'languages', []) or [],
            "completed_projects": getattr(worker, 'total_jobs', 0) or 0,
            "member_since": worker.created_at.isoformat() if hasattr(worker, 'created_at') and worker.created_at else None,
        },

        # Service review details used by mobile detail screens
        "reviews": [
            {
                "id": review.id,
                "service_id": review.service_id,
                "reviewee_id": review.reviewee_id,
                "reviewer_id": review.reviewer_id,
                "rating": float(review.rating),
                "comment": review.comment,
                "reviewer_name": (
                    f"{review.reviewer.first_name} {review.reviewer.last_name}".strip()
                    if review.reviewer
                    else None
                ),
                "reviewer_first_name": review.reviewer.first_name if review.reviewer else None,
                "reviewer_last_name": review.reviewer.last_name if review.reviewer else None,
                "reviewer_avatar": review.reviewer.avatar_url if review.reviewer else None,
                "created_at": review.created_at.isoformat() if review.created_at else None,
                "updated_at": review.updated_at.isoformat() if review.updated_at else None,
            }
            for review in service_reviews
        ],
        "total_reviews": service_total_reviews,
        "average_rating": service_average_rating,
    }

@router.put("/{service_id}", response_model=ServiceInDB)
async def update_service(
    service_id: int,
    service: ServiceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update an existing service.
    """
    result = await db.execute(select(Service).filter(Service.id == service_id))
    db_service = result.scalars().first()
    if not db_service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found.")
    
    if db_service.worker_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this service.",
        )
    
    update_data = service.dict(exclude_unset=True)

    if "category_id" in update_data:
        category_input = update_data["category_id"]
        category = await _resolve_category(db, category_input)
        if not category:
            valid_categories = ", ".join(FRONTEND_TO_DB_CATEGORIES.keys())
            if isinstance(category_input, int) or (isinstance(category_input, str) and category_input.isdigit()):
                detail = f"Category with id {category_input} does not exist."
            else:
                detail = f"Category '{category_input}' does not exist. Valid categories: {valid_categories}"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail,
            )
        update_data["category_id"] = category.id
    for key, value in update_data.items():
        setattr(db_service, key, value)
    
    db.add(db_service)
    await db.flush()
    await db.commit()
    
    # Convert to dict to avoid lazy-loading
    # Fetch category name
    category_result = await db.execute(
        select(Category).filter(Category.id == db_service.category_id)
    )
    category = category_result.scalars().first()
    category_name = category.name if category else None
    
    service_dict = {
        "id": db_service.id,
        "name": db_service.name,
        "description": db_service.description,
        "price": db_service.price,
        "pricing_model": db_service.pricing_model,
        "estimated_delivery_time": db_service.estimated_delivery_time,
        "revisions": db_service.revisions,
        "tags": db_service.tags or [],
        "worker_id": db_service.worker_id,
        "category_id": db_service.category_id,
        "category_name": category_name,
    }
    
    return ServiceInDB(**service_dict)

@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a service.
    """
    result = await db.execute(select(Service).filter(Service.id == service_id))
    db_service = result.scalars().first()
    if not db_service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found.")
    
    if db_service.worker_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this service.",
        )
    
    await db.delete(db_service)
    await db.flush()
    return

@router.get("/search/all", response_model=dict)
async def search_and_filter_services(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    search_query: str = "",
    min_price: float = 0,
    max_price: float = float('inf'),
    min_revisions: int = 0,
    pricing_model: str = None,
    category_id: int = None,
    city: str = None,
    min_delivery_days: int = 0,
    max_delivery_days: int = 999,
    sort_by: str = "newest",
    skip: int = 0,
    limit: int = 20,
):
    """
    Search and filter services with comprehensive filtering options.
    
    Query Parameters:
    - search_query: Search in service name, description, and tags
    - min_price: Minimum service price
    - max_price: Maximum service price
    - min_revisions: Minimum number of revisions
    - pricing_model: Filter by pricing model (fixed_price, hourly, milestone)
    - category_id: Filter by category ID
    - city: Filter by worker's city
    - min_delivery_days: Minimum delivery time in days
    - max_delivery_days: Maximum delivery time in days
    - skip: Pagination offset
    - limit: Results per page (max 100)
    """
    try:
        print(f"\n📡 [Backend] GET /services/search/all endpoint called")
        print(f"   - Search query: '{search_query}'")
        print(f"   - Price range: ₦{min_price} - ₦{max_price}")
        print(f"   - Revisions: {min_revisions}+")
        print(f"   - Pricing model: {pricing_model}")
        print(f"   - Category ID: {category_id}")
        print(f"   - City: {city}")
        print(f"   - Delivery days: {min_delivery_days} - {max_delivery_days}")
        
        # Build base query
        query = select(Service).filter(Service.worker_id != current_user.id)
        
        # Search query filter (name, description, tags)
        if search_query:
            search_term = f"%{search_query}%"
            query = query.filter(
                (Service.name.ilike(search_term)) |
                (Service.description.ilike(search_term))
            )
        
        # Price range filter
        if min_price > 0:
            query = query.filter(Service.price >= min_price)
        if max_price < float('inf'):
            query = query.filter(Service.price <= max_price)
        
        # Revisions filter
        if min_revisions > 0:
            query = query.filter(Service.revisions >= min_revisions)
        
        # Pricing model filter
        if pricing_model:
            query = query.filter(Service.pricing_model == pricing_model)
        
        # Category filter
        if category_id:
            query = query.filter(Service.category_id == category_id)
        
        # City filter
        if city:
            query = query.filter(Service.city.ilike(f"%{city}%"))
        
        # Delivery days filter (parse estimated_delivery_time string like "2 days", "3 weeks")
        if min_delivery_days > 0 or max_delivery_days < 999:
            # For now, store delivery time as string like "5 days", "1 week", etc.
            # This is a basic filter - you may need to enhance this based on your format
            pass  # Implement if delivery_time parsing is needed
        
        # Ensure SQL functions are available
        from sqlalchemy import func

        # Apply sorting
        if sort_by == "price_asc":
            query = query.order_by(Service.price.asc())
        elif sort_by == "price_desc":
            query = query.order_by(Service.price.desc())
        elif sort_by == "rating_desc":
            # Join with User to sort by reputation_score
            from sqlalchemy.orm import joinedload
            query = query.join(User, Service.worker_id == User.id).order_by(User.reputation_score.desc(), Service.created_at.desc())
        else:  # newest (default)
            query = query.order_by(Service.created_at.desc())

        # Get total count before pagination
        count_query = select(func.count(Service.id)).select_from(Service)
        if search_query:
            search_term = f"%{search_query}%"
            count_query = count_query.filter(
                (Service.name.ilike(search_term)) |
                (Service.description.ilike(search_term))
            )
        if min_price > 0:
            count_query = count_query.filter(Service.price >= min_price)
        if max_price < float('inf'):
            count_query = count_query.filter(Service.price <= max_price)
        if min_revisions > 0:
            count_query = count_query.filter(Service.revisions >= min_revisions)
        if pricing_model:
            count_query = count_query.filter(Service.pricing_model == pricing_model)
        if category_id:
            count_query = count_query.filter(Service.category_id == category_id)
        if city:
            count_query = count_query.filter(Service.city.ilike(f"%{city}%"))
        count_query = count_query.filter(Service.worker_id != current_user.id)
        
        total_result = await db.execute(count_query)
        total_count = total_result.scalar() or 0
        
        # Apply pagination
        limit = min(limit, 100)  # Cap at 100
        query = query.offset(skip).limit(limit)
        
        # Execute query
        result = await db.execute(query)
        services = result.scalars().all()
        
        print(f"✅ [Backend] Found {len(services)} services (total: {total_count})")
        
        # Enrich services with worker and image data
        enriched_services = []
        for service in services:
            # Get worker details
            worker_result = await db.execute(
                select(User).filter(User.id == service.worker_id)
            )
            worker = worker_result.scalars().first()
            
            # Get images
            images_result = await db.execute(
                select(File).filter(
                    File.reference_id == service.id,
                    File.reference_type == "service"
                )
            )
            images = images_result.scalars().all()
            
            # Get category
            category_result = await db.execute(
                select(Category).filter(Category.id == service.category_id)
            )
            category = category_result.scalars().first()
            
            # Count reviews for worker
            from sqlalchemy import func
            from app.models.review import Review
            reviews_result = await db.execute(
                select(func.count(Review.id)).where(
                    Review.reviewee_id == worker.id
                )
            )
            total_reviews = reviews_result.scalar() or 0
            
            service_dict = {
                "id": service.id,
                "name": service.name,
                "description": service.description,
                "price": float(service.price),
                "pricing_model": service.pricing_model,
                "estimated_delivery_time": service.estimated_delivery_time,
                "revisions": service.revisions,
                "tags": service.tags or [],
                "city": service.city,
                "country": service.country,
                "latitude": service.latitude,
                "longitude": service.longitude,
                "category_id": service.category_id,
                "category_name": category.name if category else None,
                "image_url": images[0].file_path if images else None,
                "worker": {
                    "id": worker.id,
                    "first_name": worker.first_name,
                    "last_name": worker.last_name,
                    "avatar_url": worker.avatar_url,
                    "rating": float(worker.reputation_score) if worker.reputation_score else 0.0,
                    "total_reviews": int(total_reviews),
                } if worker else None,
                "created_at": service.created_at.isoformat() if service.created_at else None,
            }
            enriched_services.append(service_dict)
        
        return {
            "items": enriched_services,
            "total": total_count,
            "skip": skip,
            "limit": limit,
        }
        
    except Exception as e:
        print(f"❌ [Backend] Error in GET /services/search/all: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching services: {str(e)}"
        )


@router.get("/{service_id}", response_model=ServiceDetailResponse)
async def get_service_detail(
    service_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get enriched service details including worker info, reviews, and images.
    """
    try:
        print(f"\n📡 [Backend] GET /services/{service_id} endpoint called")
        
        # Fetch the service
        result = await db.execute(
            select(Service).filter(Service.id == service_id)
        )
        service = result.scalars().first()
        
        if not service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service with ID {service_id} not found"
            )
        
        # Fetch worker details
        worker_result = await db.execute(
            select(User).filter(User.id == service.worker_id)
        )
        worker = worker_result.scalars().first()
        
        # Get category
        category_result = await db.execute(
            select(Category).filter(Category.id == service.category_id)
        )
        category = category_result.scalars().first()
        
        # Get images for service
        images_result = await db.execute(
            select(File).filter(
                (File.reference_id == service.id) &
                (File.reference_type == "service")
            )
        )
        images = images_result.scalars().all()
        
        # Get reviews for this service and calculate stats
        from sqlalchemy import func
        reviews_result = await db.execute(
            select(Review)
            .filter(
                Review.service_id == service.id,
                Review.reviewee_id == service.worker_id
            )
            .order_by(Review.created_at.desc())
            .limit(3)
        )
        recent_reviews = reviews_result.scalars().all()
        
        # Count total reviews and calculate average rating
        count_result = await db.execute(
            select(
                func.count(Review.id),
                func.avg(Review.rating)
            ).where(
                Review.service_id == service.id,
                Review.reviewee_id == service.worker_id
            )
        )
        total_reviews, avg_rating = count_result.first()
        total_reviews = total_reviews or 0
        avg_rating = float(avg_rating) if avg_rating else 0.0
        
        # Get worker reviews for completion rate and response time
        worker_reviews_result = await db.execute(
            select(Review).filter(Review.reviewee_id == service.worker_id)
        )
        worker_reviews = worker_reviews_result.scalars().all()
        
        # Calculate worker stats (if available - using placeholder logic)
        completion_rate = None
        response_time_hours = None
        if worker_reviews:
            avg_rating_worker = sum(r.rating for r in worker_reviews) / len(worker_reviews)
        
        # Build response
        response_data = {
            "id": service.id,
            "name": service.name,
            "description": service.description,
            "price": float(service.price),
            "pricing_model": service.pricing_model,
            "estimated_delivery_time": service.estimated_delivery_time,
            "revisions": service.revisions,
            "tags": service.tags or [],
            "city": service.city,
            "country": service.country,
            "latitude": service.latitude,
            "longitude": service.longitude,
            "category_id": service.category_id,
            "category_name": category.name if category else None,
            "image_url": images[0].file_path if images else None,
            "images": [
                {
                    "id": img.id,
                    "file_path": img.file_path,
                    "reference_id": img.reference_id
                }
                for img in images
            ] if images else None,
            "worker": {
                "id": worker.id,
                "first_name": worker.first_name,
                "last_name": worker.last_name,
                "avatar_url": worker.avatar_url,
                "rating": float(worker.reputation_score) if worker.reputation_score else 0.0,
                "total_reviews": len(worker_reviews),
                "completion_rate": completion_rate,
                "response_time_hours": response_time_hours,
            } if worker else None,
            "reviews": [
                {
                    "id": r.id,
                    "rating": float(r.rating),
                    "comment": r.comment,
                    "reviewer_first_name": r.reviewer.first_name if r.reviewer else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in recent_reviews
            ] if recent_reviews else None,
            "total_reviews": int(total_reviews),
            "average_rating": avg_rating,
            "created_at": service.created_at.isoformat() if service.created_at else None,
        }
        
        print(f"✅ [Backend] Service detail retrieved successfully")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [Backend] Error in GET /services/{service_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching service details: {str(e)}"
        )


@router.get("/nearby/list")
async def get_nearby_services(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_km: Optional[int] = None,
    city: Optional[str] = None,
    category_id: Optional[int] = None,
    limit: int = 50,
):
    """Get services nearby the user's location.
    
    Query parameters:
    - latitude: User's latitude (uses current user's location if not provided)
    - longitude: User's longitude (uses current user's location if not provided)
    - city: Optional city name for reference
    - radius_km: Search radius in kilometers (uses user's preference if not provided)
    - category_id: Optional category filter
    - limit: Maximum results (default 50, max 200)
    
    Uses location coordinates to find nearby services within the specified radius.
    """
    from app.services.location_service import LocationService
    import logging
    
    # Validate limit
    limit = min(int(limit), 200) if limit else 50
    
    # Use provided location or fall back to user's stored location
    if latitude is None or longitude is None:
        if current_user.latitude is None or current_user.longitude is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location not provided. Please provide latitude and longitude or set your location in profile."
            )
        latitude = current_user.latitude
        longitude = current_user.longitude
    
    # Validate coordinates
    try:
        latitude = float(latitude)
        longitude = float(longitude)
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise ValueError("Invalid coordinates")
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid latitude/longitude values"
        )
    
    try:
        location_service = LocationService(db)
        radius_km = location_service.resolve_search_radius_km(user=current_user, radius_km=radius_km)
        logger = logging.getLogger(__name__)
        logger.info(f"[get_nearby_services] User {current_user.id} searching at ({latitude}, {longitude}), radius={radius_km}km{f', city={city}' if city else ''}")
        nearby_services = await location_service.get_nearby_services(
            user_latitude=latitude,
            user_longitude=longitude,
            radius_km=radius_km,
            category_id=category_id,
            limit=limit
        )
        
        logger.info(f"[get_nearby_services] Found {len(nearby_services)} services for user {current_user.id}")
    except Exception as e:
        logger.error(f"[get_nearby_services] Error fetching nearby services: {str(e)}")
        return []
    
    # Convert to response format with distance and comprehensive worker info
    result = []
    for service, distance in nearby_services:
        images_result = await db.execute(
            select(File).filter(
                (File.reference_id == service.id) &
                (File.reference_type == "service")
            )
        )
        images = images_result.scalars().all()

        service_data = {
            "id": service.id,
            "title": service.name,
            "name": service.name,
            "description": service.description,
            "price": float(service.price or 0),
            "priceValue": float(service.price or 0),
            "pricing_model": service.pricing_model,
            "hourly_rate": float(service.hourly_rate or 0) if service.pricing_model == "hourly_rate" else None,
            "starting_price": float(service.price or 0),
            "city": service.city,
            "country": service.country,
            "distance_km": round(distance, 2),
            "latitude": service.latitude,
            "longitude": service.longitude,
            "worker_id": service.worker_id,
            "image_url": images[0].file_path if images else None,
            "images": [
                {
                    "id": img.id,
                    "file_path": img.file_path,
                    "original_filename": img.original_filename,
                }
                for img in images
            ],
            "created_at": service.created_at.isoformat() if service.created_at else None,
            "updated_at": service.updated_at.isoformat() if service.updated_at else None,
        }
        
        # Add worker info if relationship is loaded
        if service.worker:
            first_name = service.worker.first_name or ''
            last_name = service.worker.last_name or ''
            worker_name = f"{first_name} {last_name}".strip() or "Provider"
            
            service_data["worker_name"] = worker_name
            service_data["workerName"] = worker_name
            service_data["worker"] = {
                "id": service.worker.id,
                "first_name": first_name,
                "last_name": last_name,
                "full_name": worker_name,
                "avatar_url": service.worker.avatar_url,
                "rating": float(service.worker.reputation_score or 4.7),
            }
            service_data["average_rating"] = float(service.worker.reputation_score or 4.7)
            service_data["worker_rating"] = float(service.worker.reputation_score or 4.7)
        else:
            service_data["worker_name"] = "Provider"
            service_data["workerName"] = "Provider"
            service_data["average_rating"] = 4.7
            service_data["worker_rating"] = 4.7
        
        # Availability status
        service_data["is_available"] = getattr(service, 'is_available', True)
        service_data["available"] = getattr(service, 'is_available', True)
        service_data["status"] = getattr(service, 'status', 'active')
        
        # Category info
        if hasattr(service, 'category_id') and service.category_id:
            service_data["category_id"] = service.category_id
        if hasattr(service, 'category_name') and service.category_name:
            service_data["category_name"] = service.category_name
        
        result.append(service_data)
    
    return result


@router.get("/requests/pending", response_model=BookingListResponse)
async def get_pending_service_requests(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get pending service booking requests for the current worker.
    """
    if current_user.role != UserRole.WORKER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only workers can view pending requests")

    pending_statuses = [BookingStatus.BOOKED, BookingStatus.PENDING]
    query = (
        select(Booking)
        .where(
            Booking.worker_id == current_user.id,
            Booking.status.in_(pending_statuses),
        )
        .options(selectinload(Booking.service), selectinload(Booking.employer), selectinload(Booking.worker))
        .order_by(Booking.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    count_query = select(func.count(Booking.id)).where(
        Booking.worker_id == current_user.id,
        Booking.status.in_(pending_statuses),
    )

    result = await db.execute(query)
    items = result.scalars().unique().all()
    total_result = await db.execute(count_query)
    total = int(total_result.scalar() or 0)

    return BookingListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[BookingResponse.model_validate(item) for item in items],
    )


@router.get("/recommendations", response_model=List[dict])
async def get_service_recommendations(
    limit: int = 8,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recommend service categories based on recent booking demand.
    Returns a list of categories with booking counts.
    """
    query = (
        select(Category.id, Category.name, func.count(Booking.id))
        .join(Service, Service.category_id == Category.id)
        .join(Booking, Booking.service_id == Service.id, isouter=True)
        .group_by(Category.id, Category.name)
        .order_by(func.count(Booking.id).desc())
        .limit(limit)
    )
    result = await db.execute(query)
    rows = result.all()
    return [
        {
            "category_id": row[0],
            "category_name": row[1],
            "booking_count": int(row[2] or 0),
        }
        for row in rows
    ]
