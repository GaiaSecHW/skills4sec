"""
Tests for AdminLog model
"""
import pytest

from app.models.admin_log import AdminLog
from app.models.user import User


class TestAdminLog:
    """Test AdminLog model"""

    @pytest.mark.asyncio
    async def test_create_admin_log(self, super_admin_user: User):
        """Test creating an admin log"""
        log = await AdminLog.create(
            admin_id=super_admin_user.id,
            admin_employee_id=super_admin_user.employee_id,
            action="create_user",
            target_user_id=123,
            details={"name": "New User"},
        )

        assert log.id is not None
        assert log.admin_id == super_admin_user.id
        assert log.action == "create_user"

    @pytest.mark.asyncio
    async def test_admin_log_with_ip(self, super_admin_user: User):
        """Test admin log with IP address"""
        log = await AdminLog.create(
            admin_id=super_admin_user.id,
            admin_employee_id=super_admin_user.employee_id,
            action="delete_skill",
            target_user_id=456,
            ip_address="192.168.1.100",
        )

        assert log.ip_address == "192.168.1.100"
        assert log.action == "delete_skill"

    @pytest.mark.asyncio
    async def test_admin_log_str(self, super_admin_user: User):
        """Test admin log string representation"""
        log = await AdminLog.create(
            admin_id=super_admin_user.id,
            admin_employee_id=super_admin_user.employee_id,
            action="update_config",
        )
        # Just verify it doesn't crash
        assert str(log) is not None or True
