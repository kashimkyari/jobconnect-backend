"""
Worker matching and recommendation service for employers
"""
from typing import List, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, desc

from app.models.user import User, UserRole
from app.schemas.user import UserProfile
from app.services.location_service import LocationService


class WorkerMatchingService:
    """Service for finding and recommending workers to employers"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.location_service = LocationService(db)
    
    async def get_recommended_workers(
        self,
        employer: User,
        service_category: Optional[str] = None,
        experience_level: Optional[str] = None,
        min_rating: float = 0.0,
        limit: int = 10
    ) -> List[Tuple[User, float]]:
        """
        Get recommended workers for an employer based on location and profile match.
        
        Uses a combined scoring algorithm:
        - Location score: 0.5 weight - based on distance from employer's location
        - Skills score: 0.5 weight - based on experience and reputation
        
        Args:
            employer: The employer user object
            service_category: Optional category to filter by
            experience_level: Optional experience level to filter by
            min_rating: Minimum reputation score required
            limit: Maximum number of results
            
        Returns:
            List of (User, score) tuples, sorted by score
        """
        
        # Build query for active, verified workers
        filters = [
            User.role == UserRole.WORKER,
            User.is_active == True,
            User.is_verified == True,
            User.reputation_score >= min_rating
        ]
        
        if service_category:
            filters.append(User.service_category == service_category)
        
        if experience_level:
            filters.append(User.experience_level == experience_level)
        
        query = select(User).where(and_(*filters)).limit(limit * 3)
        result = await self.db.execute(query)
        workers = result.scalars().all()
        
        scored_workers = []
        
        for worker in workers:
            # Calculate skills/reputation score
            # Normalize reputation score (assumed to be 0-5 scale)
            skills_score = min(worker.reputation_score / 5.0, 1.0) if worker.reputation_score else 0.5
            
            # Add category bonus if matches
            if service_category and worker.service_category == service_category:
                skills_score = min(skills_score + 0.2, 1.0)
            
            # Calculate location score
            location_score = 0.0
            if employer.latitude and employer.longitude and worker.latitude and worker.longitude:
                distance = self.location_service.calculate_distance(
                    employer.latitude, employer.longitude,
                    worker.latitude, worker.longitude
                )
                
                # Use employer's preferred search radius
                search_radius = self.location_service.resolve_search_radius_km(user=employer)
                max_distance = search_radius * 2
                
                if distance <= search_radius:
                    location_score = 1.0
                elif distance <= max_distance:
                    location_score = 1.0 - (distance - search_radius) / (max_distance - search_radius)
                else:
                    location_score = 0.0
            else:
                # If location data not available, give neutral score
                location_score = 0.5
            
            # Combined score: 50% location, 50% skills/reputation
            combined_score = (0.5 * location_score) + (0.5 * skills_score)
            scored_workers.append((worker, combined_score))
        
        # Sort by combined score (highest first), then by reputation
        scored_workers.sort(key=lambda x: (-x[1], -x[0].reputation_score))
        
        return scored_workers[:limit]
    
    async def get_nearby_workers(
        self,
        employer_latitude: float,
        employer_longitude: float,
        radius_km: int = 50,
        service_category: Optional[str] = None,
        experience_level: Optional[str] = None,
        min_rating: float = 0.0,
        limit: int = 50
    ) -> List[Tuple[User, float]]:
        """
        Get workers within a specific radius of an employer.
        
        Args:
            employer_latitude: Employer's latitude
            employer_longitude: Employer's longitude
            radius_km: Search radius in kilometers
            service_category: Optional category filter
            experience_level: Optional experience level filter
            min_rating: Minimum reputation score
            limit: Maximum number of results
            
        Returns:
            List of (User, distance_km) tuples, sorted by distance then rating
        """
        
        filters = [
            User.role == UserRole.WORKER,
            User.is_active == True,
            User.is_verified == True,
            User.latitude.isnot(None),
            User.longitude.isnot(None),
            User.reputation_score >= min_rating
        ]
        
        if service_category:
            filters.append(User.service_category == service_category)
        
        if experience_level:
            filters.append(User.experience_level == experience_level)
        
        query = select(User).where(and_(*filters))
        result = await self.db.execute(query)
        workers = result.scalars().all()
        
        # Calculate distances and filter by radius
        nearby_workers = []
        for worker in workers:
            distance = self.location_service.calculate_distance(
                employer_latitude, employer_longitude,
                worker.latitude, worker.longitude
            )
            
            if distance <= radius_km:
                nearby_workers.append((worker, distance))
        
        # Sort by distance, then by reputation score
        nearby_workers.sort(key=lambda x: (x[1], -x[0].reputation_score))
        
        return nearby_workers[:limit]
