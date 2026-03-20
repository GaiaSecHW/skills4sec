"""
Tests for authentication API endpoints
"""
import pytest
from httpx import AsyncClient

from app.models.user import User
from app.utils.security import get_password_hash, create_access_token


class TestLoginByEmployeeId:
    """Test login by employee ID endpoint"""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user: User):
        """Test successful login"""
        response = await client.post(
            "/api/auth/login/new",
            json={
                "employee_id": "TEST001",
                "api_key": "test-api-key-12345"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["employee_id"] == "TEST001"

    @pytest.mark.asyncio
    async def test_login_invalid_employee_id(self, client: AsyncClient):
        """Test login with non-existent employee ID"""
        response = await client.post(
            "/api/auth/login/new",
            json={
                "employee_id": "NOTEXIST",
                "api_key": "some-key"
            }
        )

        assert response.status_code == 401
        assert "工号或 API 密钥错误" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_invalid_api_key(self, client: AsyncClient, test_user: User):
        """Test login with wrong API key"""
        response = await client.post(
            "/api/auth/login/new",
            json={
                "employee_id": "TEST001",
                "api_key": "wrong-api-key"
            }
        )

        assert response.status_code == 401
        assert "工号或 API 密钥错误" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_disabled_user(self, client: AsyncClient, db):
        """Test login with disabled user"""
        # Create disabled user
        disabled_user = await User.create(
            employee_id="DISABLED001",
            api_key_hash=get_password_hash("disabled-key"),
            name="Disabled User",
            role="user",
            status="disabled",
        )

        response = await client.post(
            "/api/auth/login/new",
            json={
                "employee_id": "DISABLED001",
                "api_key": "disabled-key"
            }
        )

        assert response.status_code == 400
        assert "已被" in response.json()["detail"]


class TestRefreshToken:
    """Test token refresh endpoint"""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, client: AsyncClient, test_user: User):
        """Test successful token refresh"""
        # First login to get refresh token
        from app.utils.security import create_refresh_token

        refresh_token = create_refresh_token({"sub": "TEST001"})

        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "expires_in" in data

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, client: AsyncClient):
        """Test refresh with invalid token"""
        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid.token.here"}
        )

        assert response.status_code == 401
        assert "无效的刷新令牌" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_refresh_token_disabled_user(self, client: AsyncClient, db):
        """Test refresh with disabled user"""
        from app.utils.security import create_refresh_token

        # Create disabled user
        disabled_user = await User.create(
            employee_id="DISABLED002",
            api_key_hash=get_password_hash("disabled-key"),
            name="Disabled User 2",
            role="user",
            status="disabled",
        )

        refresh_token = create_refresh_token({"sub": "DISABLED002"})

        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token}
        )

        assert response.status_code == 401


class TestGetCurrentUser:
    """Test get current user endpoint"""

    @pytest.mark.asyncio
    async def test_get_current_user_success(
        self, client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """Test getting current user info"""
        response = await client.get("/api/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["employee_id"] == "TEST001"
        assert data["name"] == "Test User"

    @pytest.mark.asyncio
    async def test_get_current_user_no_token(self, client: AsyncClient):
        """Test getting current user without token"""
        response = await client.get("/api/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, client: AsyncClient):
        """Test getting current user with invalid token"""
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.token"}
        )

        assert response.status_code == 401
