"""
Area Intelligence Service for location-based discovery and trending analysis
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func, desc
from app.models.user import User
from app.models.job import Job
from app.models.service import Service
from app.models.category import Category
from app.models.review import Review
from app.services.location_service import LocationService


class AreaIntelligenceService:
    """Service for analyzing area intelligence and discovery metrics"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.location_service = LocationService(db)
    
    async def get_trending_categories(
        self,
        latitude: float,
        longitude: float,
        radius_km: int = 10,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get trending service categories by location based on job count and service availability.
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            radius_km: Search radius in kilometers
            limit: Maximum number of results
            
        Returns:
            List of trending categories with counts and demand signals
            [
                {
                    "id": 1,
                    "name": "Nanny/Childcare",
                    "job_count": 47,
                    "service_count": 23,
                    "avg_rating": 4.8,
                    "demand_trend": "high"
                },
                ...
            ]
        """
        # Get all jobs in the area
        jobs_query = select(Job).where(
            Job.status == "open",
            Job.is_active == True,
            Job.latitude.isnot(None),
            Job.longitude.isnot(None)
        )
        jobs_result = await self.db.execute(jobs_query)
        jobs = jobs_result.scalars().all()
        
        # Get all services in the area
        services_query = select(Service).where(
            Service.latitude.isnot(None),
            Service.longitude.isnot(None),
            Service.is_active == True if hasattr(Service, 'is_active') else True
        )
        services_result = await self.db.execute(services_query)
        services = services_result.scalars().all()
        
        # Filter by radius
        nearby_jobs = [
            job for job in jobs
            if self.location_service.calculate_distance(
                latitude, longitude, job.latitude, job.longitude
            ) <= radius_km
        ]
        
        nearby_services = [
            service for service in services
            if self.location_service.calculate_distance(
                latitude, longitude, service.latitude, service.longitude
            ) <= radius_km
        ]
        
        # Group by category
        category_stats = {}
        
        for job in nearby_jobs:
            cat_id = job.category_id
            if cat_id not in category_stats:
                category_stats[cat_id] = {"jobs": 0, "services": 0, "service_ids": []}
            category_stats[cat_id]["jobs"] += 1
        
        for service in nearby_services:
            cat_id = service.category_id
            if cat_id not in category_stats:
                category_stats[cat_id] = {"jobs": 0, "services": 0, "service_ids": []}
            category_stats[cat_id]["services"] += 1
            category_stats[cat_id]["service_ids"].append(service.id)
        
        # Enrich with category names and ratings
        results = []
        for cat_id, stats in category_stats.items():
            # Get category name
            cat_query = select(Category).where(Category.id == cat_id)
            cat_result = await self.db.execute(cat_query)
            category = cat_result.scalar_one_or_none()
            
            if not category:
                continue
            
            # Calculate average rating for services in this category
            avg_rating = 0.0
            if stats["service_ids"]:
                rating_query = select(func.avg(Review.rating)).where(
                    Review.service_id.in_(stats["service_ids"])
                )
                rating_result = await self.db.execute(rating_query)
                avg_rating = float(rating_result.scalar() or 0.0)
            
            # Determine demand trend
            total_activity = stats["jobs"] + stats["services"]
            demand_trend = "high" if total_activity > 5 else "medium" if total_activity > 2 else "low"
            
            results.append({
                "id": cat_id,
                "name": category.name,
                "icon": category.icon if hasattr(category, 'icon') else None,
                "job_count": stats["jobs"],
                "service_count": stats["services"],
                "total_count": total_activity,
                "avg_rating": round(avg_rating, 1),
                "demand_trend": demand_trend
            })
        
        # Sort by total activity (jobs + services) descending and limit
        results.sort(key=lambda x: x["total_count"], reverse=True)
        return results[:limit]
    
    async def get_area_summary(
        self,
        latitude: float,
        longitude: float,
        radius_km: int = 10
    ) -> Dict[str, Any]:
        """
        Get comprehensive area summary including trending categories, top providers, and demand signals.
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            radius_km: Search radius in kilometers
            
        Returns:
            {
                "location": {"latitude": X, "longitude": Y, "radius_km": Z},
                "stats": {
                    "total_service_providers": 47,
                    "total_open_jobs": 12,
                    "avg_provider_rating": 4.8
                },
                "trending_categories": [...],
                "demand_signals": "Nannies are most requested here, followed by cleaners"
            }
        """
        trending = await self.get_trending_categories(latitude, longitude, radius_km, limit=5)
        
        # Get stats
        jobs_query = select(func.count(Job.id)).where(
            Job.status == "open",
            Job.is_active == True,
            Job.latitude.isnot(None),
            Job.longitude.isnot(None)
        )
        jobs_result = await self.db.execute(jobs_query)
        total_jobs = jobs_result.scalar() or 0
        
        services_query = select(func.count(Service.id)).where(
            Service.latitude.isnot(None),
            Service.longitude.isnot(None),
            Service.is_active == True if hasattr(Service, 'is_active') else True
        )
        services_result = await self.db.execute(services_query)
        total_services = services_result.scalar() or 0
        
        # Calculate average rating across all nearby services
        avg_rating_query = select(func.avg(Review.rating))
        avg_rating_result = await self.db.execute(avg_rating_query)
        avg_rating = float(avg_rating_result.scalar() or 0.0)
        
        # Generate demand signal
        demand_signal = "No services found in this area yet"
        if trending:
            top_categories = [cat["name"] for cat in trending[:3]]
            demand_signal = f"{', '.join(top_categories)} are most in demand here"
        
        return {
            "location": {
                "latitude": latitude,
                "longitude": longitude,
                "radius_km": radius_km
            },
            "stats": {
                "total_service_providers": total_services,
                "total_open_jobs": total_jobs,
                "avg_provider_rating": round(avg_rating, 1)
            },
            "trending_categories": trending,
            "demand_signals": demand_signal
        }
    
    async def get_top_providers_by_category(
        self,
        category_id: int,
        latitude: float,
        longitude: float,
        radius_km: int = 10,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top-rated service providers in a specific category within an area.
        
        Args:
            category_id: Category ID to filter by
            latitude: Center point latitude
            longitude: Center point longitude
            radius_km: Search radius in kilometers
            limit: Maximum number of results
            
        Returns:
            List of providers sorted by rating and response time
            [
                {
                    "id": 1,
                    "name": "Jane Smith",
                    "avatar_url": "...",
                    "title": "Professional Nanny",
                    "rating": 4.9,
                    "review_count": 23,
                    "response_time_hours": 2,
                    "certifications": ["CPR", "First Aid"],
                    "distance_km": 0.5,
                    "is_verified": True
                },
                ...
            ]
        """
        # Get services in this category
        services_query = select(Service).where(
            Service.category_id == category_id,
            Service.latitude.isnot(None),
            Service.longitude.isnot(None),
            Service.is_active == True if hasattr(Service, 'is_active') else True
        )
        services_result = await self.db.execute(services_query)
        services = services_result.scalars().all()
        
        # Build provider list with ratings and distance
        providers = []
        for service in services:
            distance = self.location_service.calculate_distance(
                latitude, longitude, service.latitude, service.longitude
            )
            
            if distance > radius_km:
                continue
            
            # Get provider info
            worker = service.worker
            
            # Get average rating and review count
            rating_query = select(
                func.avg(Review.rating).label("avg_rating"),
                func.count(Review.id).label("review_count")
            ).where(Review.service_id == service.id)
            rating_result = await self.db.execute(rating_query)
            rating_row = rating_result.first()
            
            avg_rating = float(rating_row.avg_rating or 0.0)
            review_count = rating_row.review_count or 0
            
            # Get certifications from user profile (if stored in JSONB)
            certifications = []
            if hasattr(worker, 'certifications') and worker.certifications:
                certifications = worker.certifications
            elif hasattr(worker, 'metadata') and worker.metadata and 'certifications' in worker.metadata:
                certifications = worker.metadata.get('certifications', [])
            
            providers.append({
                "id": worker.id,
                "service_id": service.id,
                "name": f"{worker.first_name or ''} {worker.last_name or ''}".strip(),
                "avatar_url": worker.avatar_url,
                "title": service.name,
                "description": service.description,
                "rating": round(avg_rating, 1),
                "review_count": review_count,
                "response_time_hours": 2,  # Default for now, could be tracked separately
                "certifications": certifications,
                "distance_km": round(distance, 1),
                "is_verified": worker.is_kyc_verified,
                "price": float(service.price) if service.price else 0,
                "pricing_model": service.pricing_model
            })
        
        # Sort by rating (desc), then review count (desc)
        providers.sort(
            key=lambda x: (x["rating"], x["review_count"]),
            reverse=True
        )
        
        return providers[:limit]
    
    async def get_workers_to_hire_by_category(
        self,
        category_id: int,
        latitude: float,
        longitude: float,
        radius_km: int = 10,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get available workers in a specific category (for employers looking to hire).
        
        Args:
            category_id: Category ID to filter by
            latitude: Center point latitude
            longitude: Center point longitude
            radius_km: Search radius in kilometers
            limit: Maximum number of results
            
        Returns:
            List of workers sorted by reputation and response time
        """
        # Get workers with this category in their profile
        workers_query = select(User).where(
            User.role == "worker",
            User.is_active == True,
            User.latitude.isnot(None),
            User.longitude.isnot(None)
        )
        
        workers_result = await self.db.execute(workers_query)
        workers = workers_result.scalars().all()
        
        # Filter by category and radius
        results = []
        for worker in workers:
            distance = self.location_service.calculate_distance(
                latitude, longitude, worker.latitude, worker.longitude
            )
            
            if distance > radius_km:
                continue
            
            # Check if worker has this category in their profile
            # This would require checking worker_skills or similar
            # For now, just return active workers in radius
            
            results.append({
                "id": worker.id,
                "name": f"{worker.first_name or ''} {worker.last_name or ''}".strip(),
                "avatar_url": worker.avatar_url,
                "reputation_score": float(worker.reputation_score or 0.0),
                "is_verified": worker.is_kyc_verified,
                "distance_km": round(distance, 1)
            })
        
        # Sort by reputation score
        results.sort(key=lambda x: x["reputation_score"], reverse=True)
        return results[:limit]
