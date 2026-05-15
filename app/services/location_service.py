"""
Location-based services for calculating distances and finding nearby entities
"""
import math
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_
from sqlalchemy.orm import selectinload

from app.models.user import User, UserRole
from app.models.job import Job, JobLocationType
from app.models.service import Service


class LocationService:
    """Service for location-based calculations and queries"""
    
    EARTH_RADIUS_KM = 6371  # Earth's radius in kilometers
    DEFAULT_SEARCH_RADIUS_KM = 50
    MAX_SEARCH_RADIUS_KM = 500
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    @staticmethod
    def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Calculate the great circle distance between two points on the earth (in kilometers).
        Uses Haversine formula.
        
        Args:
            lat1, lng1: First point coordinates
            lat2, lng2: Second point coordinates
            
        Returns:
            Distance in kilometers
        """
        if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
            return float('inf')
        
        # Convert decimal degrees to radians
        lat1_rad = math.radians(lat1)
        lng1_rad = math.radians(lng1)
        lat2_rad = math.radians(lat2)
        lng2_rad = math.radians(lng2)
        
        # Differences
        dlat = lat2_rad - lat1_rad
        dlng = lng2_rad - lng1_rad
        
        # Haversine formula
        a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return LocationService.EARTH_RADIUS_KM * c

    @classmethod
    def resolve_search_radius_km(
        cls,
        user: Optional[User] = None,
        radius_km: Optional[int] = None,
        fallback_radius_km: Optional[int] = None,
    ) -> int:
        """Resolve an effective radius, preferring an explicit override then the user's preference."""
        resolved_radius = radius_km

        if resolved_radius is None and user is not None:
            resolved_radius = getattr(user, "search_radius_km", None)

        if resolved_radius is None:
            resolved_radius = fallback_radius_km

        if resolved_radius is None:
            resolved_radius = cls.DEFAULT_SEARCH_RADIUS_KM

        return max(1, min(int(resolved_radius), cls.MAX_SEARCH_RADIUS_KM))
    
    async def get_nearby_jobs(
        self,
        worker_latitude: float,
        worker_longitude: float,
        radius_km: int = 50,
        category_id: Optional[int] = None,
        experience_level: Optional[str] = None,
        limit: int = 50
    ) -> List[Tuple[Job, float]]:
        """
        Get jobs nearby a worker's location.
        
        Args:
            worker_latitude: Worker's latitude
            worker_longitude: Worker's longitude
            radius_km: Search radius in kilometers
            category_id: Optional category filter
            experience_level: Optional experience level filter
            limit: Maximum number of results
            
        Returns:
            List of (Job, distance_km) tuples, sorted by distance
        """
        # Query open jobs (do not require coords here so REMOTE jobs are included)
        query = select(Job).options(
            selectinload(Job.employer)
        ).where(
            Job.status == "open"
        )
        
        if category_id:
            query = query.where(Job.category_id == category_id)
        
        if experience_level:
            query = query.where(Job.experience_level == experience_level)
        
        result = await self.db.execute(query)
        jobs = result.scalars().all()
        
        # Calculate distances and apply rules:
        # - REMOTE jobs: always include (distance = None)
        # - HYBRID jobs: include only if job has coords and distance <= radius_km
        # - ONSITE jobs: include only if job has coords and distance <= radius_km
        onsite_and_hybrid = []
        remote_jobs = []

        for job in jobs:
            loc_type = job.location_type

            # Remote jobs: always include
            if loc_type == JobLocationType.REMOTE:
                remote_jobs.append((job, None))
                continue

            # Need coordinates for hybrid/onsite
            if job.latitude is None or job.longitude is None:
                # Can't compute distance; skip jobs without coords for onsite/hybrid
                continue

            distance = self.calculate_distance(
                worker_latitude, worker_longitude,
                job.latitude, job.longitude
            )

            # HYBRID: include only if within requested radius
            if loc_type == JobLocationType.HYBRID:
                if distance <= radius_km:
                    onsite_and_hybrid.append((job, distance))
                continue

            # ONSITE: include if within requested radius
            if loc_type == JobLocationType.ONSITE:
                if distance <= radius_km:
                    onsite_and_hybrid.append((job, distance))
                continue

        # Sort onsite/hybrid by distance
        onsite_and_hybrid.sort(key=lambda x: x[1])

        # Combine: onsite/hybrid first, then remote jobs
        combined = onsite_and_hybrid + remote_jobs

        return combined[:limit]
    
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
        Get workers nearby an employer's location.
        
        Args:
            employer_latitude: Employer's latitude
            employer_longitude: Employer's longitude
            radius_km: Search radius in kilometers
            service_category: Optional service category filter
            experience_level: Optional experience level filter
            min_rating: Minimum reputation score filter
            limit: Maximum number of results
            
        Returns:
            List of (User, distance_km) tuples, sorted by distance
        """
        filters = [
            User.role == UserRole.WORKER,
            User.latitude.isnot(None),
            User.longitude.isnot(None),
            User.is_active == True,
            User.is_verified == True,
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
            distance = self.calculate_distance(
                employer_latitude, employer_longitude,
                worker.latitude, worker.longitude
            )
            
            if distance <= radius_km:
                nearby_workers.append((worker, distance))
        
        # Sort by distance, then by reputation score (descending)
        nearby_workers.sort(key=lambda x: (x[1], -x[0].reputation_score))
        
        return nearby_workers[:limit]
    
    async def get_nearby_services(
        self,
        user_latitude: float,
        user_longitude: float,
        radius_km: int = 50,
        category_id: Optional[int] = None,
        limit: int = 50
    ) -> List[Tuple[Service, float]]:
        """
        Get services nearby a user's location.
        
        Args:
            user_latitude: User's latitude
            user_longitude: User's longitude
            radius_km: Search radius in kilometers
            category_id: Optional category filter
            limit: Maximum number of results
            
        Returns:
            List of (Service, distance_km) tuples, sorted by distance
        """
        from sqlalchemy.orm import joinedload
        
        query = select(Service).options(
            joinedload(Service.worker),
            joinedload(Service.category)
        ).where(
            Service.latitude.isnot(None),
            Service.longitude.isnot(None)
        )
        
        if category_id:
            query = query.where(Service.category_id == category_id)
        
        result = await self.db.execute(query)
        services = result.unique().scalars().all()
        
        # Calculate distances and filter by radius
        nearby_services = []
        for service in services:
            distance = self.calculate_distance(
                user_latitude, user_longitude,
                service.latitude, service.longitude
            )
            
            if distance <= radius_km:
                nearby_services.append((service, distance))
        
        # Sort by distance
        nearby_services.sort(key=lambda x: x[1])
        
        return nearby_services[:limit]
    
    async def get_user_location(self, user_id: int) -> Optional[Tuple[float, float]]:
        """
        Get a user's location coordinates.
        
        Args:
            user_id: User ID
            
        Returns:
            Tuple of (latitude, longitude) or None if not set
        """
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalars().first()
        
        if user and user.latitude and user.longitude:
            return (user.latitude, user.longitude)
        
        return None
    
    async def update_user_location(
        self,
        user_id: int,
        latitude: float,
        longitude: float,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        search_radius_km: Optional[int] = None
    ) -> Optional[User]:
        """
        Update a user's location information.
        
        Args:
            user_id: User ID
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            city: City name (optional)
            state: State/Province name (optional)
            country: Country name (optional)
            search_radius_km: Preferred search radius (optional)
            
        Returns:
            Updated User object or None if user not found
        """
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalars().first()
        
        if not user:
            return None
        
        user.latitude = latitude
        user.longitude = longitude
        
        if city is not None:
            user.city = city
        if state is not None:
            user.state = state
        if country is not None:
            user.country = country
        if search_radius_km is not None:
            user.search_radius_km = search_radius_km
        
        await self.db.commit()
        await self.db.refresh(user)
        
        return user
    
    @staticmethod
    def format_distance(distance_km: float) -> str:
        """
        Format distance for display purposes.
        
        Args:
            distance_km: Distance in kilometers
            
        Returns:
            Formatted string (e.g., "1.2 km", "45 m", etc.)
        """
        if distance_km < 0.001:
            return "< 1 m"
        elif distance_km < 1:
            meters = int(distance_km * 1000)
            return f"{meters} m"
        elif distance_km < 100:
            return f"{distance_km:.1f} km"
        else:
            return f"{int(distance_km)} km"
    
    @staticmethod
    def get_city_from_coordinates(latitude: float, longitude: float) -> str:
        """
        Simple fallback to get approximate city name from coordinates.
        In production, you'd use a reverse geocoding API like Google Maps or Nominatim.
        
        For now, returns a generic label.
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            City name or coordinate string
        """
        # This is a placeholder. In production, use reverse geocoding API
        return f"Location ({latitude:.2f}, {longitude:.2f})"
    
    async def get_nearby_jobs_with_distance(
        self,
        worker_latitude: float,
        worker_longitude: float,
        radius_km: int = 50,
        category_id: Optional[int] = None,
        experience_level: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get jobs nearby a worker's location with distance included.
        
        Args:
            worker_latitude: Worker's latitude
            worker_longitude: Worker's longitude
            radius_km: Search radius in kilometers (default 50km)
            category_id: Optional category filter
            experience_level: Optional experience level filter
            limit: Maximum number of results
            
        Returns:
            List of dicts containing job data and distance_km
        """
        nearby_jobs = await self.get_nearby_jobs(
            worker_latitude=worker_latitude,
            worker_longitude=worker_longitude,
            radius_km=radius_km,
            category_id=category_id,
            experience_level=experience_level,
            limit=limit
        )
        
        # Convert tuples to dicts with distance
        result = []
        for job, distance_km in nearby_jobs:
            if distance_km is None:
                job_dict = {
                    "job": job,
                    "distance_km": None,
                    "distance_display": "Remote"
                }
            else:
                job_dict = {
                    "job": job,
                    "distance_km": round(distance_km, 2),
                    "distance_display": self.format_distance(distance_km)
                }
            result.append(job_dict)
        
        return result
    
    async def get_nearby_workers_with_distance(
        self,
        employer_latitude: float,
        employer_longitude: float,
        radius_km: int = 50,
        service_category: Optional[str] = None,
        experience_level: Optional[str] = None,
        min_rating: float = 0.0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get workers nearby an employer's location with distance included.
        
        Args:
            employer_latitude: Employer's latitude
            employer_longitude: Employer's longitude
            radius_km: Search radius in kilometers (default 50km)
            service_category: Optional service category filter
            experience_level: Optional experience level filter
            min_rating: Minimum reputation score filter
            limit: Maximum number of results
            
        Returns:
            List of dicts containing worker data and distance_km
        """
        nearby_workers = await self.get_nearby_workers(
            employer_latitude=employer_latitude,
            employer_longitude=employer_longitude,
            radius_km=radius_km,
            service_category=service_category,
            experience_level=experience_level,
            min_rating=min_rating,
            limit=limit
        )
        
        # Convert tuples to dicts with distance
        result = []
        for worker, distance_km in nearby_workers:
            worker_dict = {
                "worker": worker,
                "distance_km": round(distance_km, 2),
                "distance_display": self.format_distance(distance_km)
            }
            result.append(worker_dict)
        
        return result
    
    async def get_nearby_services_with_distance(
        self,
        user_latitude: float,
        user_longitude: float,
        radius_km: int = 50,
        category_id: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get services nearby a user's location with distance included.
        
        Args:
            user_latitude: User's latitude
            user_longitude: User's longitude
            radius_km: Search radius in kilometers (default 50km)
            category_id: Optional category filter
            limit: Maximum number of results
            
        Returns:
            List of dicts containing service data and distance_km
        """
        nearby_services = await self.get_nearby_services(
            user_latitude=user_latitude,
            user_longitude=user_longitude,
            radius_km=radius_km,
            category_id=category_id,
            limit=limit
        )
        
        # Convert tuples to dicts with distance
        result = []
        for service, distance_km in nearby_services:
            service_dict = {
                "service": service,
                "distance_km": round(distance_km, 2),
                "distance_display": self.format_distance(distance_km)
            }
            result.append(service_dict)
        
        return result
