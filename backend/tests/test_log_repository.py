"""
Tests for Log Repository - 日志仓库测试
"""
import pytest
from datetime import datetime, timedelta

from app.repositories.log_repository import LoginLogRepository, AdminLogRepository
from app.models.login_log import LoginLog
from app.models.admin_log import AdminLog
from app.models.user import User
from app.utils.security import get_password_hash


class TestLoginLogRepository:
    """Test login log repository"""

    @pytest.fixture
    async def setup_logs(self, db, test_user):
        """Setup test login logs"""
        # Create some login logs
        await LoginLog.create(
            employee_id=test_user.employee_id,
            status="success",
            login_time=datetime.utcnow() - timedelta(hours=1),
            ip_address="192.168.1.1",
        )
        await LoginLog.create(
            employee_id=test_user.employee_id,
            status="failed",
            login_time=datetime.utcnow() - timedelta(minutes=30),
            ip_address="192.168.1.2",
            error_message="Invalid API key",
        )
        await LoginLog.create(
            employee_id="OTHER001",
            status="success",
            login_time=datetime.utcnow(),
            ip_address="192.168.1.3",
        )

    @pytest.mark.asyncio
    async def test_find_by_employee_id(self, db, setup_logs, test_user):
        """Test finding logs by employee ID"""
        repo = LoginLogRepository()
        logs = await repo.find_by_employee_id(test_user.employee_id)

        assert len(logs) >= 2  # At least 2 logs for test_user

    @pytest.mark.asyncio
    async def test_find_by_employee_id_pagination(self, db, setup_logs, test_user):
        """Test pagination in find_by_employee_id - 边界值"""
        repo = LoginLogRepository()

        # Test skip and limit
        logs = await repo.find_by_employee_id(test_user.employee_id, skip=0, limit=1)
        assert len(logs) <= 1

    @pytest.mark.asyncio
    async def test_find_failed_attempts(self, db, setup_logs, test_user):
        """Test finding failed login attempts"""
        repo = LoginLogRepository()
        since = datetime.utcnow() - timedelta(hours=2)

        failed = await repo.find_failed_attempts(test_user.employee_id, since)

        assert len(failed) >= 1
        for log in failed:
            assert log.status == "failed"

    @pytest.mark.asyncio
    async def test_count_failed_attempts(self, db, setup_logs, test_user):
        """Test counting failed login attempts"""
        repo = LoginLogRepository()
        since = datetime.utcnow() - timedelta(hours=2)

        count = await repo.count_failed_attempts(test_user.employee_id, since)

        assert count >= 1

    @pytest.mark.asyncio
    async def test_list_with_filters_employee_id(self, db, setup_logs, test_user):
        """Test list with employee_id filter"""
        repo = LoginLogRepository()
        logs, total = await repo.list_with_filters(
            employee_id=test_user.employee_id
        )

        assert total >= 2
        for log in logs:
            assert test_user.employee_id in log.employee_id

    @pytest.mark.asyncio
    async def test_list_with_filters_status(self, db, setup_logs):
        """Test list with status filter"""
        repo = LoginLogRepository()
        logs, total = await repo.list_with_filters(status="success")

        assert total >= 1
        for log in logs:
            assert log.status == "success"

    @pytest.mark.asyncio
    async def test_list_with_filters_date_range(self, db, setup_logs):
        """Test list with date range filter - 边界值"""
        repo = LoginLogRepository()
        start = datetime.utcnow() - timedelta(hours=2)
        end = datetime.utcnow() + timedelta(hours=1)

        logs, total = await repo.list_with_filters(
            start_date=start,
            end_date=end
        )

        assert total >= 1

    @pytest.mark.asyncio
    async def test_list_with_filters_pagination(self, db, setup_logs):
        """Test list with pagination - 边界值"""
        repo = LoginLogRepository()

        # First page
        logs1, total1 = await repo.list_with_filters(skip=0, limit=1)
        # Second page
        logs2, total2 = await repo.list_with_filters(skip=1, limit=1)

        assert total1 == total2  # Total should be same
        if total1 > 1:
            assert logs1[0].id != logs2[0].id  # Different records

    @pytest.mark.asyncio
    async def test_list_with_filters_combined(self, db, setup_logs, test_user):
        """Test list with combined filters"""
        repo = LoginLogRepository()
        logs, total = await repo.list_with_filters(
            employee_id=test_user.employee_id,
            status="failed",
            skip=0,
            limit=10
        )

        assert total >= 1


class TestAdminLogRepository:
    """Test admin log repository"""

    @pytest.fixture
    async def setup_admin_logs(self, db, test_user, super_admin_user):
        """Setup test admin logs"""
        await AdminLog.create(
            admin_id=super_admin_user.id,
            admin_employee_id=super_admin_user.employee_id,
            action="create_user",
            target_user_id=test_user.id,
            target_employee_id=test_user.employee_id,
            details={"test": "data"},
        )
        await AdminLog.create(
            admin_id=super_admin_user.id,
            admin_employee_id=super_admin_user.employee_id,
            action="update_user",
            target_user_id=test_user.id,
            target_employee_id=test_user.employee_id,
        )
        await AdminLog.create(
            admin_id=test_user.id,
            admin_employee_id=test_user.employee_id,
            action="delete_user",
        )

    @pytest.mark.asyncio
    async def test_find_by_admin(self, db, setup_admin_logs, super_admin_user):
        """Test finding logs by admin"""
        repo = AdminLogRepository()
        logs = await repo.find_by_admin(super_admin_user.employee_id)

        assert len(logs) >= 2

    @pytest.mark.asyncio
    async def test_find_by_admin_pagination(self, db, setup_admin_logs, super_admin_user):
        """Test pagination in find_by_admin - 边界值"""
        repo = AdminLogRepository()
        logs = await repo.find_by_admin(
            super_admin_user.employee_id,
            skip=0,
            limit=1
        )

        assert len(logs) <= 1

    @pytest.mark.asyncio
    async def test_find_by_target(self, db, setup_admin_logs, test_user):
        """Test finding logs by target user"""
        repo = AdminLogRepository()
        logs = await repo.find_by_target(test_user.employee_id)

        assert len(logs) >= 2

    @pytest.mark.asyncio
    async def test_list_with_filters_admin_id(self, db, setup_admin_logs, super_admin_user):
        """Test list with admin_employee_id filter"""
        repo = AdminLogRepository()
        logs, total = await repo.list_with_filters(
            admin_employee_id=super_admin_user.employee_id
        )

        assert total >= 2

    @pytest.mark.asyncio
    async def test_list_with_filters_action(self, db, setup_admin_logs):
        """Test list with action filter"""
        repo = AdminLogRepository()
        logs, total = await repo.list_with_filters(action="create_user")

        assert total >= 1
        for log in logs:
            assert "create_user" in log.action

    @pytest.mark.asyncio
    async def test_list_with_filters_target(self, db, setup_admin_logs, test_user):
        """Test list with target filter"""
        repo = AdminLogRepository()
        logs, total = await repo.list_with_filters(
            target_employee_id=test_user.employee_id
        )

        assert total >= 2

    @pytest.mark.asyncio
    async def test_list_with_filters_date_range(self, db, setup_admin_logs):
        """Test list with date range - 边界值"""
        repo = AdminLogRepository()
        start = datetime.utcnow() - timedelta(hours=1)
        end = datetime.utcnow() + timedelta(hours=1)

        logs, total = await repo.list_with_filters(
            start_date=start,
            end_date=end
        )

        assert total >= 1

    @pytest.mark.asyncio
    async def test_list_with_filters_pagination(self, db, setup_admin_logs):
        """Test pagination - 边界值"""
        repo = AdminLogRepository()

        logs, total = await repo.list_with_filters(skip=0, limit=2)

        assert len(logs) <= 2

    @pytest.mark.asyncio
    async def test_list_with_filters_combined(self, db, setup_admin_logs, super_admin_user):
        """Test combined filters"""
        repo = AdminLogRepository()
        logs, total = await repo.list_with_filters(
            admin_employee_id=super_admin_user.employee_id,
            action="create",
            skip=0,
            limit=10
        )

        # Should work without error
        assert total >= 0
