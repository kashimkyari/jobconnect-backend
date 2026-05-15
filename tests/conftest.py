import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import get_db
from app.db.base import Base # Import from app.db.base instead
from app.config import settings
import asyncio
from app.models.user import User
from app.schemas.user import UserCreate
from app.utils.security import get_password_hash
import time

# Create a new database for testing
TEST_DATABASE_URL = settings.DATABASE_URL.replace("jobconnect", "jobconnect_test")

@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create a new async engine for each test function."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=True,
        pool_pre_ping=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine) -> AsyncSession:
    """Provide a database session for each test function."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=async_engine, class_=AsyncSession
    )
    async with TestingSessionLocal() as session:
        async with session.begin():
            yield session

@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession):
    """Provide an async client for making API requests."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    try:
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> dict:
    """Create a test user in the database."""
    timestamp = int(time.time())
    user_data = UserCreate(
        email=f"test_{timestamp}@example.com",
        password="Password123!",
        full_name="Test User",
        phone=f"+1{timestamp}",
        role="worker"
    )
    
    user_create_dict = user_data.model_dump()
    password = user_create_dict.pop("password")
    
    user = User(**user_create_dict, hashed_password=get_password_hash(password), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role.value
    }

@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient, test_user: dict) -> dict:
    """Provide authentication headers for a test user."""
    login_data = {
        "email": test_user["email"],
        "password": "Password123!"
    }
    response = await async_client.post("/api/v1/auth/login", json=login_data)
    if response.status_code != 200:
        pytest.fail(f"Login failed: {response.status_code} - {response.text}")
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest_asyncio.fixture
async def employer_user(db_session: AsyncSession) -> dict:
    """Create an employer test user in the database."""
    timestamp = int(time.time())
    user_data = UserCreate(
        email=f"employer_{timestamp}@example.com",
        password="Password123!",
        full_name="Employer User",
        phone=f"+2{timestamp}",
        role="employer"
    )
    
    user_create_dict = user_data.model_dump()
    password = user_create_dict.pop("password")

    user = User(**user_create_dict, hashed_password=get_password_hash(password))
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role.value
    }
