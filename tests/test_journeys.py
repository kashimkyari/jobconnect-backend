import pytest
from httpx import AsyncClient
import time

API_V1_PREFIX = "/api/v1"

@pytest.fixture(scope="session")
def state():
    """A dictionary to pass state between tests across the session."""
    return {}

@pytest.fixture(scope="session")
def timestamp():
    """Provides a unique timestamp for the test session."""
    return str(int(time.time()))

@pytest.mark.dependency()
@pytest.mark.asyncio
class TestUserJourneys:
    """A class to encapsulate the end-to-end user journey tests."""

    async def test_register_employer(self, async_client: AsyncClient, timestamp, state):
        employer_email = f"employer_{timestamp}@example.com"
        employer_phone = f"+1{timestamp}"
        state["employer_data"] = {
            "email": employer_email,
            "password": "Password123!",
            "full_name": "Test Employer",
            "phone": employer_phone,
            "role": "employer"
        }
        response = await async_client.post(f"{API_V1_PREFIX}/auth/register", json=state["employer_data"])
        assert response.status_code == 201
        state["employer_id"] = response.json()["id"]

    @pytest.mark.dependency(depends=["test_register_employer"])
    async def test_login_employer(self, async_client: AsyncClient, state):
        # Manually verify the user for the test
        from app.database import SessionLocal
        from app.models.user import User
        async with SessionLocal() as db:
            user = await db.get(User, state["employer_id"])
            user.is_verified = True
            await db.commit()

        login_data = {"email": state["employer_data"]["email"], "password": "Password123!"}
        response = await async_client.post(f"{API_V1_PREFIX}/auth/login", json=login_data)
        assert response.status_code == 200
        state["employer_headers"] = {"Authorization": f"Bearer {response.json()['access_token']}"}

    @pytest.mark.dependency(depends=["test_login_employer"])
    async def test_post_job(self, async_client: AsyncClient, state):
        job_data = {
            "title": "Senior Backend Developer",
            "description": "Looking for a skilled backend developer.",
            "requirements": "5+ years of experience with Python and FastAPI.",
            "budget": 75000.0,
            "location": "Remote",
            "location_type": "remote"
        }
        response = await async_client.post(f"{API_V1_PREFIX}/jobs/", json=job_data, headers=state["employer_headers"])
        assert response.status_code == 201
        state["job_id"] = response.json()["id"]

    @pytest.mark.dependency(depends=["test_post_job"])
    async def test_register_worker(self, async_client: AsyncClient, timestamp, state):
        worker_email = f"worker_{timestamp}@example.com"
        worker_phone = f"+2{timestamp}"
        state["worker_data"] = {
            "email": worker_email,
            "password": "Password123!",
            "full_name": "Test Worker",
            "phone": worker_phone,
            "role": "worker"
        }
        response = await async_client.post(f"{API_V1_PREFIX}/auth/register", json=state["worker_data"])
        assert response.status_code == 201
        state["worker_id"] = response.json()["id"]

    @pytest.mark.dependency(depends=["test_register_worker"])
    async def test_login_worker(self, async_client: AsyncClient, state):
        # Manually verify the user for the test
        from app.database import SessionLocal
        from app.models.user import User
        async with SessionLocal() as db:
            user = await db.get(User, state["worker_id"])
            user.is_verified = True
            await db.commit()

        login_data = {"email": state["worker_data"]["email"], "password": "Password123!"}
        response = await async_client.post(f"{API_V1_PREFIX}/auth/login", json=login_data)
        assert response.status_code == 200
        state["worker_headers"] = {"Authorization": f"Bearer {response.json()['access_token']}"}

    @pytest.mark.dependency(depends=["test_login_worker"])
    async def test_apply_for_job(self, async_client: AsyncClient, state):
        application_data = {
            "cover_letter": "I am the best developer for this job.",
            "proposed_budget": 70000.0,
            "payment_required": False
        }
        response = await async_client.post(
            f"{API_V1_PREFIX}/jobs/{state['job_id']}/apply",
            json=application_data,
            headers=state["worker_headers"]
        )
        assert response.status_code == 201
        state["application_id"] = response.json()["id"]
