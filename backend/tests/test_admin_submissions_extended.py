"""
Tests for Admin Submissions API - 边界值和异常测试（极简工作流版本）
"""
import pytest
from httpx import AsyncClient

from app.models.submission import Submission, SubmissionStatus


class TestAdminSubmissionListExtended:
    """Extended tests for admin submission list"""

    @pytest.mark.asyncio
    async def test_list_submissions_with_filters(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test listing with multiple filters"""
        response = await client.get(
            "/api/admin/submissions?status=pending&page=1&page_size=10",
            headers=super_auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_submissions_pagination_boundary(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test pagination boundaries - 边界值"""
        # Page 0 (invalid)
        response = await client.get(
            "/api/admin/submissions?page=0",
            headers=super_auth_headers,
        )
        assert response.status_code in [200, 422]

        # Very large page
        response = await client.get(
            "/api/admin/submissions?page=99999",
            headers=super_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["total"] >= 0

        # Page size boundary
        response = await client.get(
            "/api/admin/submissions?page_size=100",
            headers=super_auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_submissions_invalid_status(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test with invalid status filter - 边界值"""
        response = await client.get(
            "/api/admin/submissions?status=invalid_status",
            headers=super_auth_headers,
        )
        # Should either ignore invalid status or return empty
        assert response.status_code in [200, 422]


class TestAdminSubmissionDetail:
    """Test admin submission detail"""

    @pytest.mark.asyncio
    async def test_get_submission_not_found(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test getting non-existent submission - 边界值"""
        response = await client.get(
            "/api/admin/submissions/99999",
            headers=super_auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_submission_invalid_id(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test with invalid ID format - 边界值"""
        response = await client.get(
            "/api/admin/submissions/abc",
            headers=super_auth_headers,
        )
        assert response.status_code in [400, 404, 422]


class TestAdminSubmissionStart:
    """Test admin submission start workflow"""

    @pytest.mark.asyncio
    async def test_start_submission_unauthorized(self, client: AsyncClient, db):
        """Test starting submission without auth"""
        submission = await Submission.create(
            submission_id="start-test-1",
            name="Test",
            repo_url="https://github.com/test",
            status=SubmissionStatus.PENDING,
        )

        response = await client.post(
            f"/api/admin/submissions/{submission.id}/start"
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_start_submission_not_found(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test starting non-existent submission - 边界值"""
        response = await client.post(
            "/api/admin/submissions/99999/start",
            headers=super_auth_headers,
        )
        assert response.status_code == 404


class TestAdminSubmissionRetryStep:
    """Test admin submission retry-step"""

    @pytest.mark.asyncio
    async def test_retry_step_unauthorized(self, client: AsyncClient, db):
        """Test retry-step without auth"""
        submission = await Submission.create(
            submission_id="retry-step-test-1",
            name="Test",
            repo_url="https://github.com/test",
            status=SubmissionStatus.FAILED,
            error_message="Clone failed",
        )

        response = await client.post(
            f"/api/admin/submissions/{submission.id}/retry-step",
            json={"step": "cloning"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_retry_step_not_found(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test retry-step non-existent submission - 边界值"""
        response = await client.post(
            "/api/admin/submissions/99999/retry-step",
            headers=super_auth_headers,
            json={"step": "cloning"}
        )
        assert response.status_code == 404


class TestAdminSubmissionDelete:
    """Test admin submission delete"""

    @pytest.mark.asyncio
    async def test_delete_submission_unauthorized(self, client: AsyncClient, db):
        """Test deleting submission without auth"""
        submission = await Submission.create(
            submission_id="delete-test-1",
            name="Test",
            repo_url="https://github.com/test",
            status=SubmissionStatus.COMPLETED,
        )

        response = await client.delete(
            f"/api/admin/submissions/{submission.id}"
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_submission_not_found(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test deleting non-existent submission - 边界值"""
        response = await client.delete(
            "/api/admin/submissions/99999",
            headers=super_auth_headers,
        )
        assert response.status_code == 404


class TestAdminSubmissionStats:
    """Test admin submission statistics"""

    @pytest.mark.asyncio
    async def test_get_stats_success(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test getting submission statistics"""
        response = await client.get(
            "/api/admin/submissions/stats",
            headers=super_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "total" in data["data"]
        assert "pending" in data["data"]
        assert "completed" in data["data"]
        assert "failed" in data["data"]

    @pytest.mark.asyncio
    async def test_get_stats_unauthorized(self, client: AsyncClient):
        """Test getting stats without auth"""
        response = await client.get("/api/admin/submissions/stats")
        assert response.status_code == 401


class TestAdminSubmissionCreate:
    """Test admin submission creation"""

    @pytest.mark.asyncio
    async def test_create_submission_success(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test creating submission"""
        response = await client.post(
            "/api/admin/submissions",
            headers=super_auth_headers,
            json={
                "repo_url": "https://github.com/test/new-skill",
                "name": "New Skill",
                "description": "Test skill"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    @pytest.mark.asyncio
    async def test_create_submission_unauthorized(self, client: AsyncClient):
        """Test creating submission without auth"""
        response = await client.post(
            "/api/admin/submissions",
            json={"repo_url": "https://github.com/test/skill"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_submission_missing_repo_url(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test creating submission without repo_url - 边界值"""
        response = await client.post(
            "/api/admin/submissions",
            headers=super_auth_headers,
            json={"name": "Test"}
        )
        assert response.status_code == 422


class TestAdminSubmissionDetailSuccess:
    """Test admin submission detail with data"""

    @pytest.mark.asyncio
    async def test_get_submission_detail_success(
        self, client: AsyncClient, super_auth_headers: dict, db
    ):
        """Test getting submission detail with events"""
        submission = await Submission.create(
            submission_id="detail-success-1",
            name="Detail Test",
            repo_url="https://github.com/test/detail",
            status=SubmissionStatus.COMPLETED,
            current_step="completed",
            step_details={
                "cloning": {"status": "completed", "duration": 2.5},
                "generating": {"status": "completed", "duration": 15.3},
                "migrating": {"status": "completed", "duration": 1.2}
            }
        )

        response = await client.get(
            f"/api/admin/submissions/{submission.id}",
            headers=super_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "submission" in data["data"]
        assert "events" in data["data"]
        assert data["data"]["submission"]["current_step"] == "completed"
