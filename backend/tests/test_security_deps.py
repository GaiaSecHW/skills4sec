"""
Tests for security utility dependency functions
"""
import pytest
from fastapi import HTTPException

from app.utils.security import (
    get_current_admin_user,
    get_current_superuser,
    get_current_super_admin,
)
from app.models.user import User
from app.utils.security import get_password_hash


class TestGetCurrentAdminUser:
    """Test get_current_admin_user dependency"""

    @pytest.mark.asyncio
    async def test_admin_user_passes(self, admin_user: User):
        """Test admin user passes"""
        result = await get_current_admin_user(admin_user)
        assert result == admin_user

    @pytest.mark.asyncio
    async def test_super_admin_passes(self, super_admin_user: User):
        """Test super admin passes admin check"""
        result = await get_current_admin_user(super_admin_user)
        assert result == super_admin_user

    @pytest.mark.asyncio
    async def test_regular_user_fails(self, test_user: User):
        """Test regular user fails admin check"""
        with pytest.raises(HTTPException) as exc:
            await get_current_admin_user(test_user)
        assert exc.value.status_code == 403


class TestGetCurrentSuperuser:
    """Test get_current_superuser dependency"""

    @pytest.mark.asyncio
    async def test_superuser_passes(self, super_admin_user: User):
        """Test superuser passes"""
        result = await get_current_superuser(super_admin_user)
        assert result == super_admin_user

    @pytest.mark.asyncio
    async def test_admin_fails(self, admin_user: User):
        """Test admin fails superuser check"""
        with pytest.raises(HTTPException) as exc:
            await get_current_superuser(admin_user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_regular_user_fails(self, test_user: User):
        """Test regular user fails superuser check"""
        with pytest.raises(HTTPException) as exc:
            await get_current_superuser(test_user)
        assert exc.value.status_code == 403


class TestGetCurrentSuperAdmin:
    """Test get_current_super_admin dependency"""

    @pytest.mark.asyncio
    async def test_super_admin_passes(self, super_admin_user: User):
        """Test super admin passes"""
        result = await get_current_super_admin(super_admin_user)
        assert result == super_admin_user

    @pytest.mark.asyncio
    async def test_admin_fails(self, admin_user: User):
        """Test admin fails super admin check"""
        with pytest.raises(HTTPException) as exc:
            await get_current_super_admin(admin_user)
        assert exc.value.status_code == 403


class TestUserModelMethods:
    """Test User model methods"""

    @pytest.mark.asyncio
    async def test_user_str(self, test_user: User):
        """Test User string representation"""
        assert "TEST001" in str(test_user)
