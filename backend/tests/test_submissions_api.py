"""
Tests for Submissions API endpoints
"""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

from app.models.submission import Submission, SubmissionStatus


class TestSubmitSkill:
    """Test skill submission endpoint"""

    @pytest.mark.asyncio
    async def test_submit_skill_success(self, client: AsyncClient):
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
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["issue_number"] == 123

    @pytest.mark.asyncio
    async def test_submit_skill_missing_name(self, client: AsyncClient):
        """Test submission with missing name"""
        response = await client.post(
            "/api/submissions",
            json={
                "repo_url": "https://github.com/test/skill",
                "description": "A test skill"
            }
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_skill_missing_repo_url(self, client: AsyncClient):
        """Test submission with missing repo URL"""
        response = await client.post(
            "/api/submissions",
            json={
                "name": "Test Skill",
                "description": "A test skill"
            }
        )

        assert response.status_code == 422


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
