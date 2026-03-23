"""
Tests for Submissions API endpoints
"""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock

from app.models.submission import Submission, SubmissionStatus


class TestSubmitSkill:
    """Test skill submission endpoint"""

    @pytest.mark.asyncio
    async def test_submit_skill_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful skill submission"""
        with patch("app.api.submissions.create_gitea_issue", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = (True, "Issue created", {
                "number": 123,
                "html_url": "https://gitea.example.com/issues/123"
            })

            response = await client.post(
                "/api/submissions",
                json={
                    "name": "Test Skill",
                    "repo_url": "https://github.com/test/skill",
                    "description": "A test skill",
                    "category": "security",
                    "contact": "test@example.com"
                },
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["issue_number"] == 123

    @pytest.mark.asyncio
    async def test_submit_skill_missing_name(self, client: AsyncClient, auth_headers: dict):
        """Test submission with missing name"""
        response = await client.post(
            "/api/submissions",
            json={
                "repo_url": "https://github.com/test/skill",
                "description": "A test skill"
            },
            headers=auth_headers
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_skill_missing_repo_url(self, client: AsyncClient, auth_headers: dict):
        """Test submission with missing repo URL"""
        response = await client.post(
            "/api/submissions",
            json={
                "name": "Test Skill",
                "description": "A test skill"
            },
            headers=auth_headers
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_skill_unauthorized(self, client: AsyncClient):
        """Test submission without auth"""
        response = await client.post(
            "/api/submissions",
            json={
                "name": "Test Skill",
                "repo_url": "https://github.com/test/skill",
                "description": "A test skill"
            }
        )

        assert response.status_code == 401


class TestGetSubmissionStatus:
    """Test get submission status endpoint"""

    @pytest.mark.asyncio
    async def test_get_submission_status_success(self, client: AsyncClient):
        """Test getting submission status"""
        submission = await Submission.create(
            submission_id="test-uuid-123",
            name="Test Skill",
            repo_url="https://github.com/test/skill",
            description="Test",
            status=SubmissionStatus.ISSUE_CREATED,
            issue_number=123,
            issue_url="https://gitea.example.com/issues/123",
        )

        response = await client.get(f"/api/submissions/{submission.submission_id}/status")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["submission_id"] == "test-uuid-123"
        assert data["data"]["status"] == "issue_created"

    @pytest.mark.asyncio
    async def test_get_submission_status_not_found(self, client: AsyncClient):
        """Test getting non-existent submission"""
        response = await client.get("/api/submissions/non-existent-uuid/status")

        assert response.status_code == 404


class TestSubmissionsHealth:
    """Test submissions health endpoint"""

    @pytest.mark.asyncio
    async def test_submissions_health(self, client: AsyncClient):
        """Test submissions health endpoint"""
        response = await client.get("/api/submissions/health")

        assert response.status_code == 200
        data = response.json()
        assert "configured" in data
        assert "gitea_url" in data


class TestSubmitSkillExtended:
    """Extended tests for skill submission"""

    @pytest.mark.asyncio
    async def test_submit_skill_with_all_fields(self, client: AsyncClient, auth_headers: dict):
        """Test submission with all optional fields"""
        with patch("app.api.submissions.create_gitea_issue", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = (True, "Issue created", {
                "number": 456,
                "html_url": "https://gitea.example.com/issues/456"
            })

            response = await client.post(
                "/api/submissions",
                json={
                    "name": "Full Skill",
                    "repo_url": "https://github.com/test/full-skill",
                    "description": "A complete skill submission",
                    "category": "security",
                    "contact": "full@example.com"
                },
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    @pytest.mark.asyncio
    async def test_submit_skill_gitea_failure(self, client: AsyncClient, auth_headers: dict):
        """Test submission when Gitea issue creation fails"""
        with patch("app.api.submissions.create_gitea_issue", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = (False, "Gitea API error", None)

            response = await client.post(
                "/api/submissions",
                json={
                    "name": "Fail Skill",
                    "repo_url": "https://github.com/test/fail-skill",
                    "description": "This will fail"
                },
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True  # Still succeeds, but schedules retry
            assert "系统会自动重试" in data["message"]

    @pytest.mark.asyncio
    async def test_submit_skill_empty_description(self, client: AsyncClient, auth_headers: dict):
        """Test submission with empty description - 边界值"""
        with patch("app.api.submissions.create_gitea_issue", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = (True, "Issue created", {"number": 789})

            response = await client.post(
                "/api/submissions",
                json={
                    "name": "Empty Desc",
                    "repo_url": "https://github.com/test/empty",
                    "description": ""
                },
                headers=auth_headers
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_submit_skill_long_name(self, client: AsyncClient, auth_headers: dict):
        """Test submission with very long name - 边界值"""
        response = await client.post(
            "/api/submissions",
            json={
                "name": "A" * 250,  # Over 200 limit
                "repo_url": "https://github.com/test/long",
                "description": "Test"
            },
            headers=auth_headers
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_skill_invalid_repo_url(self, client: AsyncClient, auth_headers: dict):
        """Test submission with invalid repo URL - 边界值"""
        with patch("app.api.submissions.create_gitea_issue", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = (True, "Issue created", {"number": 999})

            # Invalid URL but API should still accept it (just stores it)
            response = await client.post(
                "/api/submissions",
                json={
                    "name": "Invalid URL",
                    "repo_url": "not-a-valid-url",
                    "description": "Test"
                },
                headers=auth_headers
            )

            # API accepts it, validation is minimal
            assert response.status_code in [200, 422]


class TestGetMySubmissions:
    """Test get my submissions endpoint"""

    @pytest.mark.asyncio
    async def test_get_my_submissions_unauthorized(self, client: AsyncClient):
        """Test getting my submissions without auth"""
        response = await client.get("/api/submissions/my")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_my_submissions_empty(self, client: AsyncClient, auth_headers: dict):
        """Test getting my submissions when empty"""
        response = await client.get("/api/submissions/my", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 0

    @pytest.mark.asyncio
    async def test_get_my_submissions_with_data(
        self, client: AsyncClient, auth_headers: dict, test_user
    ):
        """Test getting my submissions with data"""
        # Create a submission for the test user
        await Submission.create(
            submission_id="my-sub-test",
            name="My Submission",
            repo_url="https://github.com/test/my-sub",
            description="Test",
            status=SubmissionStatus.ISSUE_CREATED,
            submitter_id=test_user.id,
            submitter_employee_id=test_user.employee_id,
        )

        response = await client.get("/api/submissions/my", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) >= 1


class TestCreateGiteaIssue:
    """Test create_gitea_issue function directly"""

    @pytest.mark.asyncio
    async def test_create_gitea_issue_success(self, db, monkeypatch):
        """Test successful Gitea issue creation"""
        from app.api.submissions import create_gitea_issue
        import httpx

        # Set token for test
        monkeypatch.setattr("app.api.submissions.GITEA_TOKEN", "test-token")

        submission = await Submission.create(
            submission_id="gitea-test",
            name="Gitea Test",
            repo_url="https://github.com/test/gitea",
            description="Test",
            category="security",
            contact="test@example.com",
            status=SubmissionStatus.CREATING_ISSUE,
        )

        # Create a proper async context manager mock
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json = MagicMock(return_value={"number": 123, "html_url": "https://gitea.test/123"})

        async def mock_post(*args, **kwargs):
            return mock_response

        class MockAsyncClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return None
            async def post(self, *args, **kwargs):
                return mock_response

        with patch("app.api.submissions.httpx.AsyncClient", return_value=MockAsyncClient()):
            success, message, data = await create_gitea_issue(submission)

            assert success is True
            assert data["number"] == 123

    @pytest.mark.asyncio
    async def test_create_gitea_issue_no_token(self, db, monkeypatch):
        """Test Gitea issue creation without token configured"""
        from app.api.submissions import create_gitea_issue

        # Temporarily set token to None
        monkeypatch.setattr("app.api.submissions.GITEA_TOKEN", None)

        submission = await Submission.create(
            submission_id="no-token-test",
            name="No Token",
            repo_url="https://github.com/test/notoken",
            status=SubmissionStatus.CREATING_ISSUE,
        )

        success, message, data = await create_gitea_issue(submission)

        assert success is False
        assert "Token" in message or "未配置" in message
        assert data is None

    @pytest.mark.asyncio
    async def test_create_gitea_issue_api_error(self, db, monkeypatch):
        """Test Gitea issue creation when API returns error - 边界值"""
        from app.api.submissions import create_gitea_issue

        monkeypatch.setattr("app.api.submissions.GITEA_TOKEN", "test-token")

        submission = await Submission.create(
            submission_id="api-error-test",
            name="API Error",
            repo_url="https://github.com/test/apierror",
            status=SubmissionStatus.CREATING_ISSUE,
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        class MockAsyncClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return None
            async def post(self, *args, **kwargs):
                return mock_response

        with patch("app.api.submissions.httpx.AsyncClient", return_value=MockAsyncClient()):
            success, message, data = await create_gitea_issue(submission)

            assert success is False
            assert "失败" in message
            assert data is None

    @pytest.mark.asyncio
    async def test_create_gitea_issue_network_error(self, db, monkeypatch):
        """Test Gitea issue creation with network error - 边界值"""
        from app.api.submissions import create_gitea_issue

        monkeypatch.setattr("app.api.submissions.GITEA_TOKEN", "test-token")

        submission = await Submission.create(
            submission_id="net-error-test",
            name="Network Error",
            repo_url="https://github.com/test/neterror",
            status=SubmissionStatus.CREATING_ISSUE,
        )

        class MockAsyncClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return None
            async def post(self, *args, **kwargs):
                raise Exception("Connection refused")

        with patch("app.api.submissions.httpx.AsyncClient", return_value=MockAsyncClient()):
            success, message, data = await create_gitea_issue(submission)

            assert success is False
            assert "网络错误" in message or "Connection refused" in message
            assert data is None
