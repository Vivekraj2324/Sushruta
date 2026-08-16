"""
Sushruta — Test Configuration & Fixtures
==========================================

Shared pytest fixtures for all test modules.

Test architecture:
- Uses in-memory SQLite with aiosqlite driver for fast, isolated tests.
- No PostgreSQL required for CI — tests run anywhere.
- Each test gets a fresh database (tables created/dropped per test).
- httpx AsyncClient talks to the FastAPI app directly (no server needed).
- Auth fixtures provide pre-authenticated headers for protected routes.

Tradeoffs:
- SQLite doesn't support pgvector — Phase 2 vector tests will need
  a PostgreSQL test container.
- SQLite has minor SQL dialect differences — tested functions should
  use standard SQL or be dialect-aware.
"""

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings, get_settings
from app.core.security import create_access_token
from app.db.database import Base, get_db
from app.db.models import Doctor  # noqa: F401 — ensure models are registered
from app.main import app


# ── Test Settings Override ───────────────────────────────────────
def get_test_settings() -> Settings:
    """Override settings for test environment."""
    return Settings(
        DATABASE_URL="sqlite+aiosqlite:///",  # In-memory SQLite
        SECRET_KEY="test-secret-key-not-for-production",
        ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=30,
        ENVIRONMENT="testing",
        DEBUG=False,
        UPLOAD_DIR="test_uploads",
        # Phase 2: Empty key = embedding functions return None gracefully
        GEMINI_API_KEY="",
        CHUNK_SIZE=512,
        CHUNK_OVERLAP=50,
        RAG_TOP_K=5,
    )


# ── Test Database Engine ─────────────────────────────────────────
test_engine = create_async_engine(
    "sqlite+aiosqlite:///",
    echo=False,
)

test_session_factory = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Database Session Override ────────────────────────────────────
async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session."""
    async with test_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Apply dependency overrides
app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_settings] = get_test_settings


# ── Event Loop Fixture ───────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for all tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Database Setup/Teardown ──────────────────────────────────────
@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """
    Create all tables before each test, drop after.

    autouse=True means every test gets a fresh database automatically.
    This ensures complete test isolation.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── HTTP Client Fixture ──────────────────────────────────────────
@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an async HTTP client for testing API endpoints.

    Uses ASGI transport to call FastAPI directly — no network involved.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ── Database Session Fixture ─────────────────────────────────────
@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a raw database session for direct DB operations in tests."""
    async with test_session_factory() as session:
        yield session


# ── Auth Helper Fixtures ─────────────────────────────────────────
@pytest_asyncio.fixture
async def registered_doctor(client: AsyncClient) -> dict:
    """
    Register a test doctor and return the response data.

    Reusable across tests that need an existing doctor.
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Dr. Test Doctor",
            "email": "test@hospital.in",
            "password": "securepassword123",
            "license_number": "MCI-TEST-001",
            "specialisation": "General Medicine",
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient, registered_doctor: dict) -> str:
    """
    Log in the test doctor and return the JWT token.
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@hospital.in",
            "password": "securepassword123",
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def auth_headers(auth_token: str) -> dict:
    """
    Return Authorization headers with Bearer token.

    Use this fixture for any test calling a protected endpoint:
        response = await client.get("/api/v1/patients", headers=auth_headers)
    """
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture
async def second_doctor_headers(client: AsyncClient) -> dict:
    """
    Register and authenticate a SECOND doctor.

    Used for data isolation tests — verifying that Doctor A
    cannot access Doctor B's patients.
    """
    # Register second doctor
    await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Dr. Second Doctor",
            "email": "second@hospital.in",
            "password": "securepassword123",
            "license_number": "MCI-TEST-002",
            "specialisation": "Cardiology",
        },
    )
    # Login
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "second@hospital.in",
            "password": "securepassword123",
        },
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
