from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, text, and_, desc, cast, Float, case, Text
from sqlalchemy.orm import selectinload
from typing import List, Optional, Any, Dict, Union
import logging
import json
from datetime import datetime, timedelta
from app.utils.cache import get_cache, set_cache

from app.models.user import User, UserRole
from app.models.service import Service
from app.models.job import Job, JobStatus
from app.models.review import Review
from app.schemas.search import SearchResult, SearchResultType, MessageSearchResult
from app.schemas.user import UserProfileWithLocation
from app.schemas.service import ServiceInDB
from app.schemas.job import JobInDB
from app.services.location_service import LocationService

logger = logging.getLogger(__name__)

class SearchService:
    @staticmethod
    async def unified_search(
        db: AsyncSession,
        q: Optional[str] = None,
        current_user_id: Optional[int] = None,
        search_type: str = "All",
        category_id: Optional[Union[str, int]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[int] = None,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        # Determine effective radius
        user = await db.get(User, current_user_id) if current_user_id else None
        effective_radius = LocationService.resolve_search_radius_km(user=user, radius_km=radius_km)

        # Cache check
        cache_key = f"search:{q}:{search_type}:{category_id}:{min_price}:{max_price}:{latitude}:{longitude}:{effective_radius}:{page}"
        cached_res = await get_cache(cache_key)
        if cached_res:
            try:
                return json.loads(cached_res)
            except:
                pass

        skip = (page - 1) * limit
        all_results = []
        
        # Prepare TSQuery if search term is provided
        # Use plainto_tsquery or websearch_to_tsquery for better flexibility
        ts_query = None
        if q and q.strip():
            # Sanitize search query for tsquery
            ts_query = func.websearch_to_tsquery('english', q)

        # --- 1. Search Sellers (Users with Worker role) ---
        if search_type in ["All", "Sellers", "Workers"]:
            user_stmt = select(User).where(User.is_active == True, User.role == UserRole.WORKER)
            
            if ts_query is not None:
                # Functional vector matching the GIN index
                vector = func.to_tsvector('english', 
                    func.coalesce(User.first_name, '') + ' ' + 
                    func.coalesce(User.last_name, '') + ' ' + 
                    func.coalesce(User.headline, '') + ' ' + 
                    func.coalesce(User.about_me, '') + ' ' + 
                    func.coalesce(User.city, '') + ' ' + 
                    func.coalesce(User.service_category, '') + ' ' +
                    func.coalesce(func.cast(User.skills, Text), '[]')
                )
                user_stmt = user_stmt.where(vector.op('@@')(ts_query))
                
                # Ranking
                rank = func.ts_rank_cd(vector, ts_query).label("text_rank")
                # Combine with reputation score (0.0 to 5.0)
                # Normalize reputation to 0-1 range and give it 30% weight
                combined_rank = (rank * 0.7 + (func.coalesce(User.reputation_score, 0) / 5.0) * 0.3).label("combined_rank")
                user_stmt = user_stmt.add_columns(combined_rank).order_by(desc("combined_rank"))
            else:
                user_stmt = user_stmt.order_by(desc(User.reputation_score), desc(User.created_at))

            if category_id:
                user_stmt = user_stmt.where(User.service_category.ilike(f"%{category_id}%"))
            
            if latitude is not None and longitude is not None:
                # Using approximate distance formula for PostgreSQL (1 degree ~ 111km)
                dist = func.sqrt(func.pow(User.latitude - latitude, 2) + func.pow(User.longitude - longitude, 2))
                user_stmt = user_stmt.where(dist <= (effective_radius / 111.0))

            user_exec = await db.execute(user_stmt.offset(skip).limit(limit))
            user_rows = user_exec.all()
            
            for row in user_rows:
                user_obj = row[0]
                try:
                    profile = UserProfileWithLocation.model_validate(user_obj)
                    profile.avg_rating = user_obj.reputation_score or 0.0
                    all_results.append(SearchResult(type=SearchResultType.WORKER, data=profile))
                except Exception as ve:
                    logger.error(f"User validation error for ID {getattr(user_obj, 'id', 'unknown')}: {str(ve)}")
                    continue

        # --- 2. Search Services (Gigs) ---
        if search_type in ["All", "Services"]:
            service_stmt = select(Service).options(selectinload(Service.category))
            if current_user_id:
                service_stmt = service_stmt.where(Service.worker_id != current_user_id)
            
            if ts_query is not None:
                vector = func.to_tsvector('english', 
                    func.coalesce(Service.name, '') + ' ' + 
                    func.coalesce(Service.description, '') + ' ' + 
                    func.coalesce(Service.city, '')
                )
                service_stmt = service_stmt.where(vector.op('@@')(ts_query))
                rank = func.ts_rank_cd(vector, ts_query).label("text_rank")
                service_stmt = service_stmt.add_columns(rank).order_by(desc("text_rank"))
            else:
                service_stmt = service_stmt.order_by(desc(Service.created_at))

            if category_id:
                if str(category_id).isdigit():
                    service_stmt = service_stmt.where(Service.category_id == int(category_id))

            if min_price:
                service_stmt = service_stmt.where(Service.price >= min_price)
            if max_price:
                service_stmt = service_stmt.where(Service.price <= max_price)
            
            if latitude is not None and longitude is not None:
                dist = func.sqrt(func.pow(Service.latitude - latitude, 2) + func.pow(Service.longitude - longitude, 2))
                service_stmt = service_stmt.where(dist <= (effective_radius / 111.0))

            service_exec = await db.execute(service_stmt.offset(skip).limit(limit))
            service_rows = service_exec.all()
            
            for row in service_rows:
                service_obj = row[0]
                try:
                    item = ServiceInDB.model_validate(service_obj)
                    item.category_name = service_obj.category.name if service_obj.category else None
                    all_results.append(SearchResult(type=SearchResultType.SERVICE, data=item))
                except Exception as ve:
                    logger.error(f"Service validation error for ID {getattr(service_obj, 'id', 'unknown')}: {str(ve)}")
                    continue

        # --- 3. Search Jobs ---
        if search_type in ["All", "Jobs"]:
            job_stmt = select(Job).where(Job.status == JobStatus.OPEN)
            
            if ts_query is not None:
                vector = func.to_tsvector('english', 
                    func.coalesce(Job.title, '') + ' ' + 
                    func.coalesce(Job.description, '') + ' ' + 
                    func.coalesce(Job.city, '')
                )
                job_stmt = job_stmt.where(vector.op('@@')(ts_query))
                rank = func.ts_rank_cd(vector, ts_query).label("text_rank")
                
                # Recency boost for jobs (within 7 days)
                recency_boost = case(
                    (Job.created_at >= (datetime.utcnow() - timedelta(days=7)), 0.2),
                    else_=0.0
                )
                combined_rank = (rank + recency_boost).label("combined_rank")
                job_stmt = job_stmt.add_columns(combined_rank).order_by(desc("combined_rank"))
            else:
                job_stmt = job_stmt.order_by(desc(Job.created_at))

            if category_id:
                job_stmt = job_stmt.where(Job.category_id == str(category_id))

            if min_price:
                job_stmt = job_stmt.where(Job.job_price >= min_price)
            if max_price:
                job_stmt = job_stmt.where(Job.job_price <= max_price)
            
            if latitude is not None and longitude is not None:
                dist = func.sqrt(func.pow(Job.latitude - latitude, 2) + func.pow(Job.longitude - longitude, 2))
                job_stmt = job_stmt.where(dist <= (effective_radius / 111.0))

            job_stmt = job_stmt.options(selectinload(Job.employer), selectinload(Job.worker))
            job_exec = await db.execute(job_stmt.offset(skip).limit(limit))
            job_rows = job_exec.all()
            
            for row in job_rows:
                job_obj = row[0]
                try:
                    all_results.append(SearchResult(type=SearchResultType.JOB, data=JobInDB.model_validate(job_obj)))
                except Exception as ve:
                    logger.error(f"Job validation error for ID {getattr(job_obj, 'id', 'unknown')}: {str(ve)}")
                    continue

        # Final trimming for "All" type if we just aggregated them
        if search_type == "All":
            all_results = all_results[:limit*3]

        response_data = {
            "results": [r.model_dump(mode='json') for r in all_results],
            "total_count": len(all_results),
            "page": page,
            "limit": limit
        }
        
        # Cache for 10 minutes
        await set_cache(cache_key, json.dumps(response_data), expire=600)
        
        return response_data
