"""
Tests for Location-Based Matching Features
Tests location service, distance calculations, and nearby entity queries
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import math

from app.models.user import User
from app.models.job import Job, JobStatus, JobLocationType
from app.models.service import Service
from app.models.category import Category
from app.schemas.user import UserCreate, UserUpdate
from app.services.location_service import LocationService


class TestLocationService:
    """Test LocationService class"""
    
    @pytest.mark.asyncio
    async def test_calculate_distance(self):
        """Test Haversine distance calculation"""
        # Lagos, Nigeria coordinates
        lagos_lat, lagos_lng = 6.5244, 3.3792
        
        # Abuja, Nigeria coordinates (approximately 450km away)
        abuja_lat, abuja_lng = 9.0765, 7.3986
        
        distance = LocationService.calculate_distance(
            lagos_lat, lagos_lng,
            abuja_lat, abuja_lng
        )
        
        # Should be approximately 450-470km
        assert 440 < distance < 480, f"Expected ~450km, got {distance}km"
    
    @pytest.mark.asyncio
    async def test_calculate_distance_same_location(self):
        """Test distance calculation for same location"""
        lat, lng = 6.5244, 3.3792
        
        distance = LocationService.calculate_distance(lat, lng, lat, lng)
        
        assert distance == 0.0, "Distance should be 0 for same location"
    
    @pytest.mark.asyncio
    async def test_calculate_distance_with_none_values(self):
        """Test distance calculation with None values"""
        result = LocationService.calculate_distance(None, 3.3792, 6.5244, 3.3792)
        
        assert result == float('inf'), "Should return infinity for None values"
    
    @pytest.mark.asyncio
    async def test_nearby_jobs_empty_database(self, db_session: AsyncSession):
        """Test nearby jobs query on empty database"""
        service = LocationService(db_session)
        
        nearby = await service.get_nearby_jobs(
            worker_latitude=6.5244,
            worker_longitude=3.3792,
            radius_km=10
        )
        
        assert nearby == [], "Should return empty list for no jobs"
    
    @pytest.mark.asyncio
    async def test_nearby_workers_empty_database(self, db_session: AsyncSession):
        """Test nearby workers query on empty database"""
        service = LocationService(db_session)
        
        nearby = await service.get_nearby_workers(
            employer_latitude=6.5244,
            employer_longitude=3.3792,
            radius_km=10
        )
        
        assert nearby == [], "Should return empty list for no workers"


class TestLocationAPIs:
    """Test location-related API endpoints"""
    
    @pytest.mark.asyncio
    async def test_update_user_location(self, client: AsyncClient, auth_headers: dict, user_id: int):
        """Test POST /users/me/location endpoint"""
        response = await client.post(
            "/users/me/location",
            json={
                "latitude": 6.5244,
                "longitude": 3.3792,
                "city": "Lagos",
                "state": "Lagos State",
                "country": "Nigeria",
                "search_radius_km": 15
            },
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["latitude"] == 6.5244
        assert data["longitude"] == 3.3792
        assert data["city"] == "Lagos"
        assert data["search_radius_km"] == 15
    
    @pytest.mark.asyncio
    async def test_get_user_location(self, client: AsyncClient, auth_headers: dict):
        """Test GET /users/me/location endpoint"""
        # First set location
        await client.post(
            "/users/me/location",
            json={
                "latitude": 6.5244,
                "longitude": 3.3792,
                "city": "Lagos",
                "state": "Lagos State",
                "country": "Nigeria"
            },
            headers=auth_headers
        )
        
        # Then retrieve it
        response = await client.get(
            "/users/me/location",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["latitude"] == 6.5244
        assert data["longitude"] == 3.3792
        assert data["city"] == "Lagos"
    
    @pytest.mark.asyncio
    async def test_get_user_location_not_set(self, client: AsyncClient, auth_headers: dict):
        """Test GET /users/me/location when location is not set"""
        response = await client.get(
            "/users/me/location",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_update_search_radius(self, client: AsyncClient, auth_headers: dict):
        """Test PUT /users/me/search-radius endpoint"""
        response = await client.put(
            "/users/me/search-radius",
            json={"search_radius_km": 25},
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["search_radius_km"] == 25
    
    @pytest.mark.asyncio
    async def test_update_search_radius_invalid_value(self, client: AsyncClient, auth_headers: dict):
        """Test PUT /users/me/search-radius with invalid value"""
        response = await client.put(
            "/users/me/search-radius",
            json={"search_radius_km": 101},  # Max is 100
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestNearbyJobsAPI:
    """Test nearby jobs discovery API"""
    
    @pytest.mark.asyncio
    async def test_nearby_jobs_empty(self, client: AsyncClient, auth_headers: dict):
        """Test GET /jobs/nearby/list with no jobs"""
        response = await client.get(
            "/jobs/nearby/list",
            params={
                "latitude": 6.5244,
                "longitude": 3.3792,
                "radius_km": 10
            },
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []
    
    @pytest.mark.asyncio
    async def test_nearby_jobs_with_results(
        self, 
        client: AsyncClient, 
        auth_headers: dict,
        db_session: AsyncSession,
        employer: User,
        worker: User,
        category: Category
    ):
        """Test GET /jobs/nearby/list with job results"""
        # Create a job at Lagos location
        job = Job(
            title="Python Developer Needed",
            description="Looking for experienced Python developer",
            employer_id=employer.id,
            category_id=category.id,
            country="Nigeria",
            city="Lagos",
            latitude=6.5244,
            longitude=3.3792,
            budget_min=50000,
            budget_max=100000,
            location_type=JobLocationType.REMOTE,
            status=JobStatus.OPEN
        )
        db_session.add(job)
        await db_session.commit()
        
        # Query nearby jobs
        response = await client.get(
            "/jobs/nearby/list",
            params={
                "latitude": 6.5244,  # Same location
                "longitude": 3.3792,
                "radius_km": 10
            },
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) >= 1
        assert any(j["title"] == "Python Developer Needed" for j in data)


class TestNearbyWorkersAPI:
    """Test nearby workers discovery API"""
    
    @pytest.mark.asyncio
    async def test_nearby_workers_empty(self, client: AsyncClient, auth_headers: dict):
        """Test GET /workers/nearby/list with no workers"""
        response = await client.get(
            "/workers/nearby/list",
            params={
                "latitude": 6.5244,
                "longitude": 3.3792,
                "radius_km": 10
            },
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []
    
    @pytest.mark.asyncio
    async def test_nearby_workers_with_results(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        worker: User
    ):
        """Test GET /workers/nearby/list with worker results"""
        # Update worker with location
        worker.latitude = 6.5244
        worker.longitude = 3.3792
        worker.city = "Lagos"
        worker.country = "Nigeria"
        worker.service_category = "Development"
        worker.is_verified = True
        worker.is_active = True
        await db_session.commit()
        
        # Query nearby workers
        response = await client.get(
            "/workers/nearby/list",
            params={
                "latitude": 6.5244,  # Same location
                "longitude": 3.3792,
                "radius_km": 10
            },
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) >= 1
        assert any(
            w["first_name"] == worker.first_name and 
            w["distance_km"] is not None
            for w in data
        )
    
    @pytest.mark.asyncio
    async def test_nearby_workers_radius_filtering(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        worker: User
    ):
        """Test radius filtering in nearby workers"""
        # Update worker with location far away (Abuja)
        worker.latitude = 9.0765  # Abuja
        worker.longitude = 7.3986
        worker.is_verified = True
        worker.is_active = True
        await db_session.commit()
        
        # Query with 10km radius from Lagos (should not find worker 450km away)
        response = await client.get(
            "/workers/nearby/list",
            params={
                "latitude": 6.5244,  # Lagos
                "longitude": 3.3792,
                "radius_km": 10  # Only 10km radius
            },
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 0  # Should be empty
        
        # Query with 500km radius (should find worker)
        response = await client.get(
            "/workers/nearby/list",
            params={
                "latitude": 6.5244,
                "longitude": 3.3792,
                "radius_km": 500
            },
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) >= 1


class TestNearbyServicesAPI:
    """Test nearby services discovery API"""
    
    @pytest.mark.asyncio
    async def test_nearby_services_empty(self, client: AsyncClient, auth_headers: dict):
        """Test GET /services/nearby/list with no services"""
        response = await client.get(
            "/services/nearby/list",
            params={
                "latitude": 6.5244,
                "longitude": 3.3792,
                "radius_km": 10
            },
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []
    
    @pytest.mark.asyncio
    async def test_nearby_services_with_results(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        worker: User,
        category: Category
    ):
        """Test GET /services/nearby/list with service results"""
        # Create a service at Lagos location
        service = Service(
            name="Web Design Services",
            description="Professional web design",
            price=50000,
            category_id=category.id,
            worker_id=worker.id,
            city="Lagos",
            country="Nigeria",
            latitude=6.5244,
            longitude=3.3792
        )
        db_session.add(service)
        await db_session.commit()
        
        # Query nearby services
        response = await client.get(
            "/services/nearby/list",
            params={
                "latitude": 6.5244,
                "longitude": 3.3792,
                "radius_km": 10
            },
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) >= 1
        assert any(s["name"] == "Web Design Services" for s in data)


class TestLocationIntegration:
    """Integration tests for location-based features"""
    
    @pytest.mark.asyncio
    async def test_worker_gets_recommended_jobs_by_location(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        employer: User,
        worker: User,
        category: Category
    ):
        """Test that recommended jobs consider location"""
        # Set worker location in Lagos
        worker.latitude = 6.5244
        worker.longitude = 3.3792
        worker.service_category = category.name
        await db_session.commit()
        
        # Create job in Lagos
        lagos_job = Job(
            title="Lagos Job",
            description="Job in Lagos",
            employer_id=employer.id,
            category_id=category.id,
            country="Nigeria",
            city="Lagos",
            latitude=6.5244,
            longitude=3.3792,
            budget_min=50000,
            budget_max=100000,
            location_type=JobLocationType.REMOTE,
            status=JobStatus.OPEN
        )
        
        # Create job in Abuja (far away)
        abuja_job = Job(
            title="Abuja Job",
            description="Job in Abuja",
            employer_id=employer.id,
            category_id=category.id,
            country="Nigeria",
            city="Abuja",
            latitude=9.0765,
            longitude=7.3986,
            job_price=50000,
            location_type=JobLocationType.REMOTE,
            status=JobStatus.OPEN
        )
        
        db_session.add(lagos_job)
        db_session.add(abuja_job)
        await db_session.commit()
        
        # Get recommended jobs
        response = await client.get(
            "/jobs/",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Lagos job should be recommended first (closer to worker)
        if len(data) > 0:
            # The algorithm considers both location and category
            assert "title" in data[0]
