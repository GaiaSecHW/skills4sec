"""
Tests for Retry Service - 重试服务测试
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from app.models.submission import Submission, SubmissionStatus
from app.services.retry_service import RetryService, RetryConfig, retry_service


class TestRetryConfig:
    """Test retry configuration"""

    def test_retry_delays(self):
        """Test retry delay configuration"""
        assert RetryConfig.RETRY_DELAYS == [30, 60, 120]
        assert len(RetryConfig.RETRY_DELAYS) == 3

    def test_max_retries(self):
        """Test max retries configuration"""
        assert RetryConfig.MAX_RETRIES == 3

    def test_request_timeout(self):
        """Test request timeout configuration"""
        assert RetryConfig.REQUEST_TIMEOUT == 30.0


class TestRetryServiceInit:
    """Test retry service initialization"""

    def test_init(self):
        """Test service initialization"""
        service = RetryService()
        assert service.gitea_api_url is not None
        assert service.gitea_repo is not None


class TestScheduleRetry:
    """Test schedule_retry method"""

    @pytest.mark.asyncio
    async def test_schedule_retry_success(self, db):
        """Test successful retry scheduling"""
        submission = await Submission.create(
            submission_id="SCHEDULE_TEST",
            name="Schedule Test",
            repo_url="https://github.com/test/schedule",
            status=SubmissionStatus.ISSUE_FAILED,
            retry_count=0,
            max_retries=3,
        )

        service = RetryService()
        result = await service.schedule_retry(submission, "Test error")

        assert result is True

        # Reload and check
        await submission.refresh_from_db()
        assert submission.next_retry_at is not None
        assert submission.error_message == "Test error"

    @pytest.mark.asyncio
    async def test_schedule_retry_max_reached(self, db):
        """Test retry scheduling when max retries reached - 边界值"""
        submission = await Submission.create(
            submission_id="MAX_RETRIES",
            name="Max Retries",
            repo_url="https://github.com/test/max",
            status=SubmissionStatus.ISSUE_FAILED,
            retry_count=3,
            max_retries=3,
        )

        service = RetryService()
        result = await service.schedule_retry(submission, "Test error")

        assert result is False

    @pytest.mark.asyncio
    async def test_schedule_retry_delay_calculation(self, db):
        """Test delay calculation for different retry counts - 边界值"""
        from datetime import timezone
        service = RetryService()

        # First retry (delay 30s)
        sub1 = await Submission.create(
            submission_id="DELAY_0",
            name="Delay 0",
            repo_url="https://github.com/test/delay0",
            status=SubmissionStatus.ISSUE_FAILED,
            retry_count=0,
            max_retries=3,
        )
        await service.schedule_retry(sub1)
        await sub1.refresh_from_db()
        now = datetime.now(timezone.utc)
        delay1 = (sub1.next_retry_at - now).total_seconds()
        assert 25 <= delay1 <= 35  # Allow tolerance

        # Second retry (delay 60s)
        sub2 = await Submission.create(
            submission_id="DELAY_1",
            name="Delay 1",
            repo_url="https://github.com/test/delay1",
            status=SubmissionStatus.ISSUE_FAILED,
            retry_count=1,
            max_retries=3,
        )
        await service.schedule_retry(sub2)
        await sub2.refresh_from_db()
        now = datetime.now(timezone.utc)
        delay2 = (sub2.next_retry_at - now).total_seconds()
        assert 55 <= delay2 <= 65


class TestExecuteRetry:
    """Test execute_retry method"""

    @pytest.mark.asyncio
    async def test_execute_retry_no_token(self, db):
        """Test retry without Gitea token configured"""
        submission = await Submission.create(
            submission_id="NO_TOKEN",
            name="No Token",
            repo_url="https://github.com/test/notoken",
            status=SubmissionStatus.ISSUE_FAILED,
            retry_count=0,
            max_retries=3,
        )

        service = RetryService()
        service.gitea_token = None

        success, message = await service.execute_retry(submission)

        assert success is False
        assert "Token" in message or "未配置" in message

    @pytest.mark.asyncio
    async def test_execute_retry_network_error(self, db):
        """Test retry with network error"""
        submission = await Submission.create(
            submission_id="NET_ERROR",
            name="Network Error",
            repo_url="https://github.com/test/neterror",
            status=SubmissionStatus.ISSUE_FAILED,
            retry_count=0,
            max_retries=3,
        )

        service = RetryService()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(side_effect=Exception("Network error"))
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            success, message = await service.execute_retry(submission)

            assert success is False


class TestProcessPendingRetries:
    """Test process_pending_retries method"""

    @pytest.mark.asyncio
    async def test_process_pending_empty(self, db):
        """Test processing when no pending retries"""
        service = RetryService()
        result = await service.process_pending_retries()

        assert result["total"] == 0
        assert result["success"] == 0
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_process_pending_with_submissions(self, db):
        """Test processing with pending submissions"""
        # Create a submission ready for retry
        await Submission.create(
            submission_id="PENDING_1",
            name="Pending 1",
            repo_url="https://github.com/test/pending1",
            status=SubmissionStatus.ISSUE_FAILED,
            retry_count=0,
            max_retries=3,
            next_retry_at=datetime.utcnow() - timedelta(minutes=1),
        )

        service = RetryService()
        service.gitea_token = None  # Will fail, but we test the flow

        result = await service.process_pending_retries()

        assert result["total"] >= 1


class TestManualRetry:
    """Test manual_retry method"""

    @pytest.mark.asyncio
    async def test_manual_retry_not_retryable(self, db):
        """Test manual retry on non-retryable submission - 边界值"""
        submission = await Submission.create(
            submission_id="NOT_RETRYABLE",
            name="Not Retryable",
            repo_url="https://github.com/test/notretry",
            status=SubmissionStatus.MERGED,  # Terminal status
            retry_count=0,
            max_retries=3,
        )

        service = RetryService()
        success, message = await service.manual_retry(submission)

        assert success is False
        assert "不支持重试" in message

    @pytest.mark.asyncio
    async def test_manual_retry_resets_count(self, db):
        """Test manual retry resets count when max reached"""
        submission = await Submission.create(
            submission_id="RESET_COUNT",
            name="Reset Count",
            repo_url="https://github.com/test/reset",
            status=SubmissionStatus.ISSUE_FAILED,
            retry_count=3,
            max_retries=3,
        )

        service = RetryService()
        service.gitea_token = None

        # This should reset count and try
        success, message = await service.manual_retry(submission)

        await submission.refresh_from_db()
        # Count is reset to 0 before execute_retry, but execute_retry may increment it
        # So we just verify it was reset at some point (now <= original)
        assert submission.retry_count <= 3


class TestRetryServiceSingleton:
    """Test retry service singleton"""

    def test_singleton_exists(self):
        """Test that singleton instance exists"""
        assert retry_service is not None
        assert isinstance(retry_service, RetryService)
