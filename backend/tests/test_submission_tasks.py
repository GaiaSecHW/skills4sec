"""
Tests for Submission Tasks - 提交定时任务测试
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from app.models.submission import Submission, SubmissionEvent, SubmissionStatus, SubmissionEventType
from app.tasks.submission_tasks import (
    process_pending_retries,
    sync_gitea_status,
    cleanup_old_events,
    cleanup_stale_submissions,
    generate_daily_stats,
    get_task_config,
)


class TestProcessPendingRetries:
    """Test process_pending_retries task"""

    @pytest.mark.asyncio
    async def test_process_pending_retries_empty(self, db):
        """Test with no pending retries"""
        with patch("app.services.retry_service.retry_service") as mock_retry:
            mock_retry.process_pending_retries = AsyncMock(return_value={
                "total": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0
            })

            result = await process_pending_retries()

            assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_process_pending_retries_with_items(self, db):
        """Test with pending retries"""
        with patch("app.services.retry_service.retry_service") as mock_retry:
            mock_retry.process_pending_retries = AsyncMock(return_value={
                "total": 3,
                "success": 2,
                "failed": 1,
                "skipped": 0
            })

            result = await process_pending_retries()

            assert result["total"] == 3
            assert result["success"] == 2


class TestSyncGiteaStatus:
    """Test sync_gitea_status task"""

    @pytest.mark.asyncio
    async def test_sync_gitea_status_empty(self, db):
        """Test with no pending syncs"""
        with patch("app.services.gitea_sync_service.gitea_sync_service") as mock_sync:
            mock_sync.sync_all_pending = AsyncMock(return_value={
                "total": 0,
                "updated": 0,
                "errors": 0
            })

            result = await sync_gitea_status()

            assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_sync_gitea_status_with_items(self, db):
        """Test with pending syncs"""
        with patch("app.services.gitea_sync_service.gitea_sync_service") as mock_sync:
            mock_sync.sync_all_pending = AsyncMock(return_value={
                "total": 5,
                "updated": 4,
                "errors": 1
            })

            result = await sync_gitea_status()

            assert result["total"] == 5
            assert result["updated"] == 4


class TestCleanupOldEvents:
    """Test cleanup_old_events task"""

    @pytest.mark.asyncio
    async def test_cleanup_old_events_empty(self, db):
        """Test with no old events"""
        result = await cleanup_old_events()

        assert result["deleted"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_old_events_with_old_events(self, db):
        """Test with old events to delete"""
        # Create a submission
        submission = await Submission.create(
            submission_id="cleanup-test",
            name="Cleanup Test",
            repo_url="https://github.com/test/cleanup",
            status=SubmissionStatus.ISSUE_CREATED,
        )

        # Create an old event (95 days ago)
        old_time = datetime.utcnow() - timedelta(days=95)
        old_event = await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.CREATED,
            new_status=SubmissionStatus.CREATING_ISSUE,
            message="Old event",
            triggered_by="user",
            created_at=old_time
        )

        result = await cleanup_old_events()

        assert result["deleted"] >= 1

    @pytest.mark.asyncio
    async def test_cleanup_old_events_keeps_recent(self, db):
        """Test that recent events are not deleted - 边界值"""
        submission = await Submission.create(
            submission_id="keep-recent-test",
            name="Keep Recent Test",
            repo_url="https://github.com/test/keep",
            status=SubmissionStatus.ISSUE_CREATED,
        )

        # Create a recent event (1 day ago)
        recent_time = datetime.utcnow() - timedelta(days=1)
        recent_event = await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.CREATED,
            new_status=SubmissionStatus.CREATING_ISSUE,
            message="Recent event",
            triggered_by="user",
            created_at=recent_time
        )

        result = await cleanup_old_events()

        # Recent event should still exist
        event_exists = await SubmissionEvent.filter(id=recent_event.id).exists()
        assert event_exists is True


class TestCleanupStaleSubmissions:
    """Test cleanup_stale_submissions task"""

    @pytest.mark.asyncio
    async def test_cleanup_stale_empty(self, db):
        """Test with no stale submissions"""
        result = await cleanup_stale_submissions()

        assert result["updated"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_stale_with_stale_submissions(self, db):
        """Test with stale submissions"""
        # Create a stale submission (8 days ago, stuck in processing)
        stale_time = datetime.utcnow() - timedelta(days=8)
        stale_submission = await Submission.create(
            submission_id="stale-test",
            name="Stale Test",
            repo_url="https://github.com/test/stale",
            status=SubmissionStatus.PROCESSING,
        )

        # Manually update updated_at to simulate stale submission
        await Submission.filter(id=stale_submission.id).update(updated_at=stale_time)

        result = await cleanup_stale_submissions()

        assert result["updated"] >= 1

        # Verify status was updated
        await stale_submission.refresh_from_db()
        assert stale_submission.status == SubmissionStatus.PROCESS_FAILED
        assert "超时" in stale_submission.error_message

    @pytest.mark.asyncio
    async def test_cleanup_stale_keeps_recent(self, db):
        """Test that recent processing submissions are not marked stale - 边界值"""
        recent_submission = await Submission.create(
            submission_id="recent-processing",
            name="Recent Processing",
            repo_url="https://github.com/test/recent",
            status=SubmissionStatus.PROCESSING,
        )

        result = await cleanup_stale_submissions()

        await recent_submission.refresh_from_db()
        assert recent_submission.status == SubmissionStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_cleanup_stale_ignores_other_statuses(self, db):
        """Test that non-processing statuses are not affected - 边界值"""
        stale_time = datetime.utcnow() - timedelta(days=8)
        other_submission = await Submission.create(
            submission_id="stale-other",
            name="Stale Other",
            repo_url="https://github.com/test/other",
            status=SubmissionStatus.ISSUE_CREATED,  # Not PROCESSING
            updated_at=stale_time
        )

        result = await cleanup_stale_submissions()

        await other_submission.refresh_from_db()
        assert other_submission.status == SubmissionStatus.ISSUE_CREATED


class TestGenerateDailyStats:
    """Test generate_daily_stats task"""

    @pytest.mark.asyncio
    async def test_generate_daily_stats_empty(self, db):
        """Test with no submissions"""
        result = await generate_daily_stats()

        assert "date" in result
        assert "total" in result
        assert "by_status" in result

    @pytest.mark.asyncio
    async def test_generate_daily_stats_with_submissions(self, db):
        """Test with yesterday's submissions"""
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        yesterday_mid = datetime.combine(yesterday, datetime.min.time())

        # Create a submission from yesterday
        await Submission.create(
            submission_id="yesterday-sub",
            name="Yesterday Sub",
            repo_url="https://github.com/test/yesterday",
            status=SubmissionStatus.ISSUE_CREATED,
            created_at=yesterday_mid
        )

        result = await generate_daily_stats()

        assert result["total"] >= 1
        assert result["date"] == yesterday.isoformat()


class TestTaskConfig:
    """Test task configuration"""

    def test_get_task_config(self):
        """Test getting task configuration"""
        config = get_task_config()

        assert process_pending_retries in config
        assert sync_gitea_status in config
        assert cleanup_old_events in config
        assert cleanup_stale_submissions in config
        assert generate_daily_stats in config

        # Check config format
        for task_func, (interval, description) in config.items():
            assert isinstance(interval, int)
            assert isinstance(description, str)
            assert interval > 0
