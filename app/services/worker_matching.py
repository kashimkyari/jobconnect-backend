"""
Worker matching service for location-based worker discovery
"""
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_

from app.models.user import User, UserRole
from app.models.job import Job
from app.services.location_service import LocationService


class WorkerMatchingService:
    """Service for matching employers with workers based on location and skills"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.location_service = LocationService(db)
    
    async def get_recommended_workers(
        self,
        employer: User,
        limit: int = 50
    ) -> List[Tuple[User, float, float]]:
        """
        Get recommended workers for an employer based on location and skills match.
        
        Uses a combined scoring algorithm:
        - Location score: 0.5 weight - based on distance from employer's location  
        - Skills score: 0.5 weight - based on completed jobs and category match
        
        Args:
            employer: Employer User object
            limit: Maximum number of workers to return
            
        Returns:
            List of (Worker, combined_score, distance_km) tuples, sorted by score desc
        """
        # Get all active, verified workers
        query = select(User).where(
            and_(
                User.role == UserRole.WORKER,
                User.is_active == True,
                User.is_verified == True
            )
        )
        
        result = await self.db.execute(query)
        workers = result.scalars().all()
        
        scored_workers = []
        
        for worker in workers:
            # Calculate skills score based on worker's completed jobs
            # Count completed jobs in last 6 months
            jobs_query = select(Job).where(
                and_(
                    Job.worker_id == worker.id,
                    Job.status == "completed"
                )
            )
            jobs_result = await self.db.execute(jobs_query)
            completed_jobs = len(jobs_result.scalars().all())
            
            # Skills score: 0.5 base + 0.5 based on completed jobs
            # Max out at 1.0 after 10 completed jobs
            skills_score = 0.5 + min(0.5, (completed_jobs / 10) * 0.5)
            
            # Calculate location score
            location_score = 0.0
            distance_km = float('inf')
            
            if employer.latitude and employer.longitude:
                if worker.latitude and worker.longitude:
                    distance_km = self.location_service.calculate_distance(
                        employer.latitude, employer.longitude,
                        worker.latitude, worker.longitude
                    )
                    
                    # Location score: 1.0 if within employer's search radius
                    search_radius = self.location_service.resolve_search_radius_km(user=employer)
                    max_distance = search_radius * 2
                    
                    if distance_km <= search_radius:
                        location_score = 1.0
                    elif distance_km <= max_distance:
                        location_score = 1.0 - (distance_km - search_radius) / (max_distance - search_radius)
                    else:
                        location_score = 0.0
                else:
                    # Worker has no location, give neutral score
                    location_score = 0.5
            else:
                # Employer has no location, give neutral location score
                location_score = 0.5
            
            # Combined score: 50% location, 50% skills
            combined_score = (0.5 * location_score) + (0.5 * skills_score)
            
            # Apply reputation bonus (if worker has good reputation)
            reputation_bonus = min(0.2, worker.reputation_score / 100 * 0.2)
            combined_score = min(1.0, combined_score + reputation_bonus)
            
            scored_workers.append((worker, combined_score, distance_km))
        
        # Sort by combined score (highest first)
        scored_workers.sort(key=lambda x: -x[1])
        
        return scored_workers[:limit]
    
    async def get_nearby_workers(
        self,
        employer_id: int,
        limit: int = 50
    ) -> Optional[List[Tuple[User, float]]]:
        """
        Get workers nearby an employer without full scoring.
        Uses only location information.
        
        Args:
            employer_id: Employer's user ID
            limit: Maximum number of workers to return
            
        Returns:
            List of (Worker, distance_km) tuples, sorted by distance, or None if employer has no location
        """
        # Get employer
        employer_query = select(User).where(User.id == employer_id)
        employer_result = await self.db.execute(employer_query)
        employer = employer_result.scalars().first()
        
        if not employer or not employer.latitude or not employer.longitude:
            return None
        
        # Get nearby workers using location service
        radius_km = self.location_service.resolve_search_radius_km(user=employer)
        nearby = await self.location_service.get_nearby_workers(
            employer.latitude,
            employer.longitude,
            radius_km=radius_km,
            limit=limit
        )
        
        return nearby
    
    async def get_workers_by_skill(
        self,
        service_category: str,
        employer_latitude: Optional[float] = None,
        employer_longitude: Optional[float] = None,
        radius_km: int = 10,
        limit: int = 50
    ) -> List[Tuple[User, Optional[float]]]:
        """
        Get workers matching a specific service category, optionally filtered by location.
        
        Args:
            service_category: Service category to search for
            employer_latitude: Optional employer latitude for distance calculation
            employer_longitude: Optional employer longitude for distance calculation
            radius_km: Search radius if employer location is provided
            limit: Maximum number of workers to return
            
        Returns:
            List of (Worker, distance_km or None) tuples
        """
        query = select(User).where(
            and_(
                User.role == UserRole.WORKER,
                User.is_active == True,
                User.is_verified == True,
                User.service_category == service_category
            )
        ).limit(limit * 2)  # Get extra to filter by location
        
        result = await self.db.execute(query)
        workers = result.scalars().all()
        
        # Filter by location if provided
        if employer_latitude and employer_longitude:
            filtered_workers = []
            for worker in workers:
                if worker.latitude and worker.longitude:
                    distance = self.location_service.calculate_distance(
                        employer_latitude, employer_longitude,
                        worker.latitude, worker.longitude
                    )
                    
                    if distance <= radius_km:
                        filtered_workers.append((worker, distance))
                else:
                    # Include workers with no location
                    filtered_workers.append((worker, None))
            
            # Sort by distance (None values last)
            filtered_workers.sort(key=lambda x: (x[1] is None, x[1] or float('inf')))
            return filtered_workers[:limit]
        else:
            # Return workers without distance info
            return [(worker, None) for worker in workers[:limit]]
