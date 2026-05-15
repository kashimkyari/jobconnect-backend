import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import User
from app.services.auth_service import AuthService
from app.schemas.user import UserCreate

async def get_user_otp(db: AsyncSession, email: str) -> str | None:
    """Fetches the OTP for a user from the database."""
    try:
        query = select(User.otp).where(User.email == email)
        result = await db.execute(query)
        otp = result.scalar_one_or_none()
        return otp
    except Exception as e:
        print(f"Error getting OTP for {email}: {e}")
        return None

from unittest.mock import AsyncMock, Mock, patch
from app.utils.security import get_password_hash, verify_password

@pytest.mark.asyncio
async def test_create_user():
    """Test user creation and password hashing"""
    db_session = AsyncMock()
    
    user_data = UserCreate(
        email="test@example.com",
        password="Password123!",
        full_name="Test User",
        phone="+1234567890",
        role="worker"
    )
    
    # Mock the database session methods
    db_session.add = AsyncMock()
    db_session.commit = AsyncMock()
    db_session.refresh = AsyncMock()
    
    # Mock the user creation
    with patch.object(AuthService, 'create_user') as mock_create:
        mock_user = Mock()
        mock_user.email = user_data.email
        mock_user.full_name = user_data.full_name
        mock_user.hashed_password = get_password_hash(user_data.password)
        mock_create.return_value = mock_user
        
        # Create the user
        created_user = await AuthService.create_user(db_session, user_data)
        
        # Verify the user was created with the correct data
        assert created_user.email == user_data.email
        assert created_user.full_name == user_data.full_name
        
        # Verify the password was hashed correctly
        assert verify_password("Password123!", created_user.hashed_password)
        assert not verify_password("WrongPassword!", created_user.hashed_password)

@pytest.mark.asyncio
async def test_get_user_by_email():
    """Test retrieving a user by email"""
    db_session = AsyncMock()
    
    # Mock the database response
    mock_user = User(
        id=1,
        email="test@example.com",
        hashed_password=get_password_hash("Password123!"),
        full_name="Test User"
    )
    
    # Configure the mock's async result
    result_mock = Mock()
    result_mock.scalar_one_or_none.return_value = mock_user
    db_session.execute.return_value = result_mock
    
    # Retrieve the user
    retrieved_user = await AuthService.get_user_by_email(db_session, "test@example.com")
    
    # Verify the correct user was retrieved
    assert retrieved_user is not None
    assert retrieved_user.email == "test@example.com"

@pytest.mark.asyncio
async def test_get_user_by_email_not_found():
    """Test retrieving a non-existent user by email"""
    db_session = AsyncMock()
    
    # Mock the database response for a non-existent user
    result_mock = Mock()
    result_mock.scalar_one_or_none.return_value = None
    db_session.execute.return_value = result_mock
    
    # Attempt to retrieve the user
    retrieved_user = await AuthService.get_user_by_email(db_session, "nonexistent@example.com")
    
    # Verify that no user was found
    assert retrieved_user is None

API_V1_PREFIX = "/api/v1"

@pytest.mark.asyncio
async def test_create_and_get_user(async_client: AsyncClient, test_user: dict):
    """Test creating and retrieving a user via API endpoints"""
    login_data = {
        "email": test_user["email"],
        "password": "Password123!"
    }
    response = await async_client.post(f"{API_V1_PREFIX}/auth/login", json=login_data)
    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(f"{API_V1_PREFIX}/users/me", headers=headers)
    
    assert response.status_code == 200
    retrieved_user = response.json()
    assert retrieved_user["email"] == test_user["email"]
    assert retrieved_user["full_name"] == test_user["full_name"]

@pytest.mark.asyncio
async def test_update_user(async_client: AsyncClient, test_user: dict):
    """Test updating a user's profile via API endpoint"""
    login_data = {
        "email": test_user["email"],
        "password": "Password123!"
    }
    response = await async_client.post(f"{API_V1_PREFIX}/auth/login", json=login_data)
    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    update_data = {
        "full_name": "Updated Test User",
        "phone": f"+{int(time.time())}"
    }
    
    response = await async_client.put(f"{API_V1_PREFIX}/users/me", headers=headers, json=update_data)
    
    assert response.status_code == 200
    updated_user = response.json()
    assert updated_user["full_name"] == "Updated Test User"
    assert updated_user["phone"] == update_data["phone"]

@pytest.mark.asyncio
async def test_get_user_by_id(async_client: AsyncClient, test_user: dict, employer_user: dict, auth_headers: dict):
    """Test retrieving a user by ID via API endpoint"""
    response = await async_client.get(f"{API_V1_PREFIX}/users/{employer_user['id']}", headers=auth_headers)
    
    assert response.status_code == 200
    retrieved_user = response.json()
    assert retrieved_user["email"] == employer_user["email"]
    assert retrieved_user["full_name"] == employer_user["full_name"]

import time

# --- Fixtures for shared data and state ---

@pytest.fixture(scope="session")
def state():
    """A dictionary to pass state between tests across the session."""
    return {}

@pytest.fixture(scope="session")  
def timestamp():
    """Provides a unique timestamp for the test session."""
    return str(int(time.time()))

from app.utils.security import get_password_hash

@pytest.mark.asyncio
class TestGeneralAPIFeatures:
    """Tests for general API features, error handling, and edge cases."""

    @pytest.mark.parametrize("user_data, expected_status", [
        ({"email": "invalid-email", "password": "Password123!", "full_name": "Test", "phone": "1234567890", "role": "worker"}, 422),
        ({"email": "test@example.com", "password": "123", "full_name": "Test", "phone": "1234567890", "role": "worker"}, 422),
        ({"email": "test@example.com", "password": "Password123!", "full_name": "Test", "phone": "1234567890", "role": "invalid"}, 422),
    ])
    async def test_registration_validation(self, async_client: AsyncClient, user_data, expected_status):
        timestamp = int(time.time())
        user_data["email"] = f"{timestamp}_{user_data['email']}"
        user_data["phone"] = f"+3{timestamp}"
        response = await async_client.post(f"{API_V1_PREFIX}/auth/register", json=user_data)
        assert response.status_code == expected_status

    async def test_unauthorized_access(self, async_client: AsyncClient):
        response = await async_client.get(f"{API_V1_PREFIX}/users/me")
        assert response.status_code == 401

    async def test_job_not_found(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.get(f"{API_V1_PREFIX}/jobs/999999", headers=auth_headers)
        assert response.status_code == 404
