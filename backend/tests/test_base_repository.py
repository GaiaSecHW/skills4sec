"""
Tests for BaseRepository - 通过 UserRepository 测试基类功能
边界值和异常测试
"""
import pytest

from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.utils.security import get_password_hash
from app.core.exceptions import NotFoundError


class TestRepositoryCreate:
    """Test create operations - 通过 UserRepository 测试"""

    @pytest.mark.asyncio
    async def test_create_success(self, db):
        """Test successful creation"""
        repo = UserRepository()

        user = await repo.create(
            employee_id="REPO001",
            name="Repo Test",
            api_key_hash=get_password_hash("test123"),
            role="user",
        )

        assert user.id is not None
        assert user.employee_id == "REPO001"

    @pytest.mark.asyncio
    async def test_create_with_all_fields(self, db):
        """Test creation with all optional fields"""
        repo = UserRepository()

        user = await repo.create(
            employee_id="REPO002",
            name="Full User",
            api_key_hash=get_password_hash("test123"),
            role="admin",
            department="IT",
            team="Backend",
            group_name="Developers",
            email="test@example.com",
        )

        assert user.department == "IT"
        assert user.team == "Backend"
        assert user.group_name == "Developers"


class TestRepositoryGetById:
    """Test get_by_id operations - 边界值测试"""

    @pytest.mark.asyncio
    async def test_get_by_id_exists(self, db, test_user: User):
        """Test getting existing record by ID"""
        repo = UserRepository()

        result = await repo.get_by_id(test_user.id)
        assert result.employee_id == test_user.employee_id

    @pytest.mark.asyncio
    async def test_get_by_id_not_exists(self, db):
        """Test getting non-existent record by ID - 边界值"""
        repo = UserRepository()

        with pytest.raises(NotFoundError):
            await repo.get_by_id(999999)

    @pytest.mark.asyncio
    async def test_get_by_id_or_none_exists(self, db, test_user: User):
        """Test get_by_id_or_none with existing record"""
        repo = UserRepository()

        result = await repo.get_by_id_or_none(test_user.id)
        assert result is not None
        assert result.employee_id == test_user.employee_id

    @pytest.mark.asyncio
    async def test_get_by_id_or_none_not_exists(self, db):
        """Test get_by_id_or_none with non-existent record - 边界值"""
        repo = UserRepository()

        result = await repo.get_by_id_or_none(999999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_boundary_min(self, db):
        """Test with minimum ID value - 边界值"""
        repo = UserRepository()

        result = await repo.get_by_id_or_none(0)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_boundary_negative(self, db):
        """Test with negative ID value - 边界值"""
        repo = UserRepository()

        result = await repo.get_by_id_or_none(-1)
        assert result is None


class TestRepositoryList:
    """Test list operations"""

    @pytest.mark.asyncio
    async def test_list_all_with_data(self, db, test_user: User):
        """Test listing with data"""
        repo = UserRepository()

        result = await repo.list_all()
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_list_all_with_pagination(self, db):
        """Test list with skip and limit - 边界值"""
        repo = UserRepository()

        # Create multiple users
        for i in range(5):
            await User.create(
                employee_id=f"LIST{i:03d}",
                name=f"User {i}",
                api_key_hash=get_password_hash("test"),
                role="user",
            )

        # Test skip
        result = await repo.list_all(skip=2)
        assert len(result) >= 3  # At least 3 remaining

        # Test limit
        result = await repo.list_all(limit=2)
        assert len(result) == 2

        # Test skip + limit
        result = await repo.list_all(skip=1, limit=2)
        assert len(result) == 2


class TestRepositoryCount:
    """Test count operations"""

    @pytest.mark.asyncio
    async def test_count_with_filters(self, db):
        """Test count with filters"""
        repo = UserRepository()

        # Create users with different roles
        await User.create(
            employee_id="COUNT001",
            name="Admin User",
            api_key_hash=get_password_hash("test"),
            role="admin",
        )
        await User.create(
            employee_id="COUNT002",
            name="Regular User",
            api_key_hash=get_password_hash("test"),
            role="user",
        )

        admin_count = await repo.count(role="admin")
        assert admin_count >= 1


class TestRepositoryExists:
    """Test exists operations"""

    @pytest.mark.asyncio
    async def test_exists_true(self, db, test_user: User):
        """Test exists returns True"""
        repo = UserRepository()

        result = await repo.exists(employee_id=test_user.employee_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self, db):
        """Test exists returns False - 边界值"""
        repo = UserRepository()

        result = await repo.exists(employee_id="NOTEXIST999")
        assert result is False


class TestRepositoryUpdate:
    """Test update operations"""

    @pytest.mark.asyncio
    async def test_update_instance(self, db, test_user: User):
        """Test updating instance"""
        repo = UserRepository()

        updated = await repo.update(test_user, name="Updated Name")
        assert updated.name == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_by_id(self, db, test_user: User):
        """Test updating by ID"""
        repo = UserRepository()

        updated = await repo.update_by_id(test_user.id, department="New Dept")
        assert updated.department == "New Dept"


class TestRepositoryDelete:
    """Test delete operations"""

    @pytest.mark.asyncio
    async def test_delete_instance(self, db):
        """Test deleting instance"""
        repo = UserRepository()

        user = await User.create(
            employee_id="DELETE001",
            name="To Delete",
            api_key_hash=get_password_hash("test"),
            role="user",
        )

        await repo.delete(user)

        result = await repo.get_by_id_or_none(user.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_by_id(self, db):
        """Test deleting by ID"""
        repo = UserRepository()

        user = await User.create(
            employee_id="DELETE002",
            name="To Delete 2",
            api_key_hash=get_password_hash("test"),
            role="user",
        )

        await repo.delete_by_id(user.id)

        result = await repo.get_by_id_or_none(user.id)
        assert result is None


class TestRepositoryPaginate:
    """Test paginate operations - 边界值测试"""

    @pytest.mark.asyncio
    async def test_paginate_first_page(self, db):
        """Test first page pagination"""
        repo = UserRepository()

        # Create users
        for i in range(15):
            await User.create(
                employee_id=f"PAGE{i:03d}",
                name=f"Page User {i}",
                api_key_hash=get_password_hash("test"),
                role="user",
            )

        result = await repo.paginate(page=1, page_size=10)
        assert "items" in result
        assert "total" in result
        assert "page" in result
        assert result["page"] == 1

    @pytest.mark.asyncio
    async def test_paginate_large_page_number(self, db):
        """Test pagination with large page number - 边界值"""
        repo = UserRepository()

        result = await repo.paginate(page=9999, page_size=10)
        assert result["items"] == []
