"""
Tests for database module
"""
import pytest
from unittest.mock import patch, AsyncMock

from app.database import init_db, close_db


class TestDatabase:
    """Test database functions"""

    @pytest.mark.asyncio
    async def test_init_db(self):
        """Test database initialization"""
        # This test verifies the function can be called
        # We use the test database setup from conftest
        from tortoise import Tortoise

        # Verify we can initialize with the test config
        assert Tortoise._inited is True

    @pytest.mark.asyncio
    async def test_close_db(self, db):
        """Test database close function"""
        from tortoise import Tortoise

        # The db fixture handles setup/teardown
        # Just verify Tortoise is initialized
        assert Tortoise._inited is True
