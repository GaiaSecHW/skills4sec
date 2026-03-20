"""
Pytest configuration and fixtures for backend tests
"""
import asyncio
import os
import sys
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from tortoise import Tortoise

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.config import settings


# Test database URL
TEST_DATABASE_URL = "sqlite://:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncGenerator:
    """Initialize test database"""
    await Tortoise.init(
        db_url=TEST_DATABASE_URL,
        modules={
            "models": [
                "app.models.user",
                "app.models.skill",
                "app.models.audit",
                "app.models.content",
                "app.models.login_log",
                "app.models.admin_log",
                "app.models.submission",
            ]
        },
    )
    await Tortoise.generate_schemas()

    yield

    await Tortoise.close_connections()


@pytest_asyncio.fixture(scope="function")
async def client(db) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for testing"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(db):
    """Create a test user"""
    from app.models.user import User
    from app.utils.security import get_password_hash

    user = await User.create(
        employee_id="TEST001",
        api_key_hash=get_password_hash("test-api-key-12345"),
        name="Test User",
        role="user",
        status="active",
        is_active=True,
    )
    return user


@pytest_asyncio.fixture
async def admin_user(db):
    """Create an admin test user"""
    from app.models.user import User
    from app.utils.security import get_password_hash

    user = await User.create(
        employee_id="ADMIN001",
        api_key_hash=get_password_hash("admin-api-key-12345"),
        name="Admin User",
        role="admin",
        status="active",
        is_active=True,
        is_superuser=False,
    )
    return user


@pytest_asyncio.fixture
async def super_admin_user(db):
    """Create a super admin test user"""
    from app.models.user import User
    from app.utils.security import get_password_hash

    user = await User.create(
        employee_id="SUPER001",
        api_key_hash=get_password_hash("super-api-key-12345"),
        name="Super Admin",
        role="super_admin",
        status="active",
        is_active=True,
        is_superuser=True,
    )
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user) -> dict:
    """Get auth headers for test user"""
    from app.utils.security import create_access_token

    token = create_access_token(data={"sub": test_user.employee_id})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_auth_headers(admin_user) -> dict:
    """Get auth headers for admin user"""
    from app.utils.security import create_access_token

    token = create_access_token(data={"sub": admin_user.employee_id})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def super_auth_headers(super_admin_user) -> dict:
    """Get auth headers for super admin"""
    from app.utils.security import create_access_token

    token = create_access_token(data={"sub": super_admin_user.employee_id})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_category(db):
    """Create a test category"""
    from app.models.skill import Category

    category = await Category.create(
        slug="test-category",
        name="Test Category",
        description="A test category",
        sort_order=1,
    )
    return category


@pytest_asyncio.fixture
async def test_skill(db, test_category):
    """Create a test skill"""
    from app.models.skill import Skill

    skill = await Skill.create(
        slug="test-skill",
        name="Test Skill",
        description="A test skill for testing",
        author="Test Author",
        category=test_category,
        risk_level="safe",
        is_blocked=False,
        safe_to_publish=True,
        source_url="https://github.com/test/test-skill",
        source_type="community",
    )
    return skill
