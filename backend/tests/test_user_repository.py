"""
Tests for User Repository - 用户仓库测试
"""
import pytest

from app.repositories.user_repository import UserRepository
from app.models.user import User


class TestUserRepository:
    """Test user repository"""

    @pytest.fixture
    async def setup_users(self, db):
        """Setup test users"""
        user1 = await User.create(
            employee_id="REPO001",
            name="Repo User 1",
            role="user",
            status="active",
        )
        user2 = await User.create(
            employee_id="REPO002",
            name="Repo User 2",
            role="admin",
            status="disabled",
        )
        return [user1, user2]

    @pytest.mark.asyncio
    async def test_find_by_employee_id(self, db, setup_users):
        """Test finding user by employee_id"""
        repo = UserRepository()
        user = await repo.find_by_employee_id("REPO001")

        assert user is not None
        assert user.name == "Repo User 1"

    @pytest.mark.asyncio
    async def test_find_by_employee_id_not_found(self, db):
        """Test finding non-existent employee_id - 边界值"""
        repo = UserRepository()
        user = await repo.find_by_employee_id("NONEXISTENT")

        assert user is None

    @pytest.mark.asyncio
    async def test_count_by_status(self, db, setup_users):
        """Test counting users by status"""
        repo = UserRepository()

        active_count = await repo.count_by_status("active")
        assert active_count >= 1

        disabled_count = await repo.count_by_status("disabled")
        assert disabled_count >= 1

    @pytest.mark.asyncio
    async def test_count_by_status_empty(self, db):
        """Test counting by non-existent status - 边界值"""
        repo = UserRepository()
        count = await repo.count_by_status("non_existent_status")

        assert count == 0

    @pytest.mark.asyncio
    async def test_update_last_login(self, db, setup_users):
        """Test updating last login time"""
        repo = UserRepository()
        user = setup_users[0]

        # Initially last_login should be None
        assert user.last_login is None

        await repo.update_last_login(user)

        await user.refresh_from_db()
        assert user.last_login is not None

    @pytest.mark.asyncio
    async def test_update_last_login_multiple_times(self, db, setup_users):
        """Test updating last login multiple times - 边界值"""
        repo = UserRepository()
        user = setup_users[0]

        await repo.update_last_login(user)
        await user.refresh_from_db()
        first_login = user.last_login

        # Small delay to ensure different timestamp
        import asyncio
        await asyncio.sleep(0.01)

        await repo.update_last_login(user)
        await user.refresh_from_db()
        second_login = user.last_login

        assert second_login >= first_login
