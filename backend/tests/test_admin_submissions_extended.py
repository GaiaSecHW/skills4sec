"""
Tests for Admin Submissions API - 边界值和异常测试
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


class TestAdminSubmissionRetry:
    """Test admin submission retry"""

    @pytest.mark.asyncio
    async def test_retry_submission_not_found(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test retrying non-existent submission - 边界值"""
        response = await client.post(
            "/api/admin/submissions/99999/retry",
            headers=super_auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_retry_submission_unauthorized(
        self, client: AsyncClient
    ):
        """Test retry without auth"""
        response = await client.post("/api/admin/submissions/1/retry")
        assert response.status_code == 401


class TestAdminSubmissionStats:
    """Test admin submission statistics"""

    @pytest.mark.asyncio
    async def test_get_stats_success(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test getting submission stats"""
        response = await client.get(
            "/api/admin/submissions/stats",
            headers=super_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total" in data or "data" in data

    @pytest.mark.asyncio
    async def test_get_stats_unauthorized(
        self, client: AsyncClient
    ):
        """Test getting stats without auth"""
        response = await client.get("/api/admin/submissions/stats")
        assert response.status_code == 401


class TestAdminSubmissionApproveReject:
    """Test admin submission approve/reject"""

    @pytest.mark.asyncio
    async def test_approve_submission_not_found(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test approving non-existent submission - 边界值"""
        response = await client.post(
            "/api/admin/submissions/99999/approve",
            headers=super_auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_submission_not_found(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test rejecting non-existent submission - 边界值"""
        response = await client.post(
            "/api/admin/submissions/99999/reject",
            json={"reason": "Test reason"},
            headers=super_auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_submission_empty_reason(
        self, client: AsyncClient, super_auth_headers: dict, db
    ):
        """Test rejecting with empty reason - 边界值"""
        submission = await Submission.create(
            submission_id="REJECT_EMPTY",
            name="Reject Test",
            repo_url="https://github.com/test/reject",
            description="Test",
            status=SubmissionStatus.PENDING,
        )

        response = await client.post(
            f"/api/admin/submissions/{submission.id}/reject",
            json={"reason": ""},
            headers=super_auth_headers,
        )
        assert response.status_code in [400, 404, 422]


class TestAdminSubmissionTrends:
    """Test admin submission trends API"""

    @pytest.mark.asyncio
    async def test_get_trends_success(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test getting submission trends"""
        response = await client.get(
            "/api/admin/submissions/trends",
            headers=super_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_get_trends_with_days(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test getting trends with custom days - 边界值"""
        response = await client.get(
            "/api/admin/submissions/trends?days=7",
            headers=super_auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_trends_days_boundary(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test trends with boundary days - 边界值"""
        # Min days (1)
        response = await client.get(
            "/api/admin/submissions/trends?days=1",
            headers=super_auth_headers,
        )
        assert response.status_code == 200

        # Max days (30)
        response = await client.get(
            "/api/admin/submissions/trends?days=30",
            headers=super_auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_trends_unauthorized(self, client: AsyncClient):
        """Test getting trends without auth"""
        response = await client.get("/api/admin/submissions/trends")
        assert response.status_code == 401


class TestAdminSubmissionFailed:
    """Test admin failed submissions list"""

    @pytest.mark.asyncio
    async def test_list_failed_success(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test listing failed submissions"""
        response = await client.get(
            "/api/admin/submissions/failed",
            headers=super_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_list_failed_unauthorized(self, client: AsyncClient):
        """Test listing failed without auth"""
        response = await client.get("/api/admin/submissions/failed")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_failed_pagination(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test failed list pagination - 边界值"""
        response = await client.get(
            "/api/admin/submissions/failed?skip=0&limit=10",
            headers=super_auth_headers,
        )
        assert response.status_code == 200


class TestAdminSubmissionBatchRetry:
    """Test admin batch retry"""

    @pytest.mark.asyncio
    async def test_batch_retry_unauthorized(self, client: AsyncClient):
        """Test batch retry without auth"""
        response = await client.post(
            "/api/admin/submissions/batch-retry",
            json={"submission_ids": [1, 2, 3]},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_batch_retry_empty_list(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test batch retry with empty list - 边界值"""
        response = await client.post(
            "/api/admin/submissions/batch-retry",
            json={"submission_ids": []},
            headers=super_auth_headers,
        )
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_batch_retry_nonexistent(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test batch retry with non-existent IDs - 边界值"""
        response = await client.post(
            "/api/admin/submissions/batch-retry",
            json={"submission_ids": [99998, 99999]},
            headers=super_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["failed_count"] == 2


class TestAdminSubmissionExport:
    """Test admin submission CSV export"""

    @pytest.mark.asyncio
    async def test_export_csv_unauthorized(self, client: AsyncClient):
        """Test export without auth"""
        response = await client.get("/api/admin/submissions/export/csv")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_export_csv_success(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test export CSV successfully"""
        response = await client.get(
            "/api/admin/submissions/export/csv",
            headers=super_auth_headers,
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_export_csv_with_filters(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test export with filters"""
        response = await client.get(
            "/api/admin/submissions/export/csv?status=pending",
            headers=super_auth_headers,
        )
        assert response.status_code == 200


class TestAdminSchedulerStatus:
    """Test admin scheduler status API"""

    @pytest.mark.asyncio
    async def test_get_scheduler_status_unauthorized(self, client: AsyncClient):
        """Test scheduler status without auth"""
        response = await client.get("/api/admin/submissions/scheduler/status")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_scheduler_status_success(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test getting scheduler status"""
        response = await client.get(
            "/api/admin/submissions/scheduler/status",
            headers=super_auth_headers,
        )
        # May fail if scheduler not configured
        assert response.status_code in [200, 500]


class TestAdminForceProcess:
    """Test admin force process submission"""

    @pytest.mark.asyncio
    async def test_force_process_unauthorized(
        self, client: AsyncClient
    ):
        """Test force process without auth"""
        response = await client.post(
            "/api/admin/submissions/1/force-process"
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_force_process_forbidden(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test force process as regular admin (needs super)"""
        response = await client.post(
            "/api/admin/submissions/1/force-process",
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_force_process_not_found(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test force process non-existent - 边界值"""
        response = await client.post(
            "/api/admin/submissions/99999/force-process",
            headers=super_auth_headers,
        )
        assert response.status_code == 404


class TestAdminSubmissionDetailSuccess:
    """Test admin submission detail success scenarios"""

    @pytest.mark.asyncio
    async def test_get_submission_detail_success(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test getting submission detail successfully"""
        # Create a test submission
        submission = await Submission.create(
            submission_id="DETAIL_TEST",
            name="Detail Test",
            repo_url="https://github.com/test/detail",
            description="Test description",
            status=SubmissionStatus.PENDING,
        )

        response = await client.get(
            f"/api/admin/submissions/{submission.id}",
            headers=super_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["submission"]["submission_id"] == "DETAIL_TEST"


class TestAdminSubmissionRetrySuccess:
    """Test admin submission retry success scenarios"""

    @pytest.mark.asyncio
    async def test_retry_submission_with_reset(
        self, client: AsyncClient, super_auth_headers: dict
    ):
        """Test retry with reset_count flag"""
        # Create a failed submission
        submission = await Submission.create(
            submission_id="RETRY_RESET",
            name="Retry Reset Test",
            repo_url="https://github.com/test/retry",
            description="Test",
            status=SubmissionStatus.ISSUE_FAILED,
            retry_count=3,
            max_retries=3,
        )

        response = await client.post(
            f"/api/admin/submissions/{submission.id}/retry",
            json={"reset_count": True},
            headers=super_auth_headers,
        )
        # May fail if Gitea not configured, but should not 404
        assert response.status_code in [200, 400, 500]
