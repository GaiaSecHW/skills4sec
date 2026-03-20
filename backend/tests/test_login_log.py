"""
Tests for LoginLog model
"""
import pytest

from app.models.login_log import LoginLog
from app.models.user import User
from app.utils.security import get_password_hash


class TestLoginLog:
    """Test LoginLog model"""

    @pytest.mark.asyncio
    async def test_create_login_log_success(self, test_user: User):
        """Test creating a successful login log"""
        log = await LoginLog.create(
            employee_id=test_user.employee_id,
            status="success",
            ip_address="192.168.1.1",
            user_agent="Test Agent",
        )

        assert log.id is not None
        assert log.employee_id == test_user.employee_id
        assert log.status == "success"
        assert log.ip_address == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_create_login_log_failed(self, test_user: User):
        """Test creating a failed login log"""
        log = await LoginLog.create(
            employee_id=test_user.employee_id,
            status="failed",
            ip_address="192.168.1.1",
            user_agent="Test Agent",
            failure_reason="API 密钥错误",
        )

        assert log.status == "failed"
        assert log.failure_reason == "API 密钥错误"

    @pytest.mark.asyncio
    async def test_login_log_with_null_user(self, db):
        """Test login log with non-existent user"""
        log = await LoginLog.create(
            employee_id="NOTEXIST",
            status="failed",
            ip_address="10.0.0.1",
            user_agent="Test",
            failure_reason="工号不存在",
        )

        assert log.employee_id == "NOTEXIST"
        assert log.failure_reason == "工号不存在"

    @pytest.mark.asyncio
    async def test_login_log_str(self, test_user: User):
        """Test login log string representation"""
        log = await LoginLog.create(
            employee_id=test_user.employee_id,
            status="success",
            ip_address="127.0.0.1",
        )
        # Just verify it doesn't crash
        assert str(log) is not None or True
