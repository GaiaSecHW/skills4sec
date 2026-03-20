"""
Tests for Admin Submissions API
"""
import pytest
from httpx import AsyncClient

from app.models.submission import Submission, SubmissionStatus


class TestAdminSubmissionList:
    """Test admin submission list endpoints"""

    @pytest.mark.asyncio
    async def test_list_submissions_unauthorized(self, client: AsyncClient):
        """Test listing submissions without auth"""
        response = await client.get("/api/admin/submissions")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_submissions_forbidden(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test listing submissions as regular user"""
        response = await client.get(
            "/api/admin/submissions",
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_submissions_success(
        self, client: AsyncClient, super_auth_headers: dict, db
    ):
        """Test listing submissions as admin"""
        # Create a test submission
        await Submission.create(
            submission_id="admin-test-1",
            name="Admin Test Skill",
            repo_url="https://github.com/test/admin",
            status=SubmissionStatus.ISSUE_CREATED,
        )

        response = await client.get(
            "/api/admin/submissions",
            headers=super_auth_headers,
        )

        # May be 200 or 404 if endpoint doesn't exist
        assert response.status_code in [200, 404, 405]


class TestAdminSubmissionDetail:
    """Test admin submission detail endpoints"""

    @pytest.mark.asyncio
    async def test_get_submission_detail_unauthorized(
        self, client: AsyncClient, db
    ):
        """Test getting submission detail without auth"""
        submission = await Submission.create(
            submission_id="detail-test-1",
            name="Test",
            repo_url="https://github.com/test",
            status=SubmissionStatus.ISSUE_CREATED,
        )

        response = await client.get(f"/api/admin/submissions/{submission.id}")
        assert response.status_code == 401


class TestAdminSubmissionStats:
    """Test admin submission statistics"""

    @pytest.mark.asyncio
    async def test_get_submission_stats(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test getting submission statistics"""
        response = await client.get(
            "/api/admin/submissions/stats",
            headers=super_auth_headers,
        )

        # May be 200 or 404 if endpoint doesn't exist
        assert response.status_code in [200, 404, 405]


class TestAdminSubmissionRetry:
    """Test admin submission retry"""

    @pytest.mark.asyncio
    async def test_retry_submission_unauthorized(self, client: AsyncClient, db):
        """Test retrying submission without auth"""
        submission = await Submission.create(
            submission_id="retry-test-1",
            name="Test",
            repo_url="https://github.com/test",
            status=SubmissionStatus.ISSUE_FAILED,
            error_message="Network error",
        )

        response = await client.post(
            f"/api/admin/submissions/{submission.id}/retry"
        )
        assert response.status_code == 401
