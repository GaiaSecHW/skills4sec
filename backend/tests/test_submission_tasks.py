"""
Tests for Submission Tasks - 提交定时任务测试（极简工作流版本）
"""
import pytest
from datetime import datetime, timedelta

from app.models.submission import Submission, SubmissionEvent, SubmissionStatus, SubmissionEventType
from app.tasks.submission_tasks import (
    cleanup_old_events,
    cleanup_stale_submissions,
    generate_daily_stats,
    get_task_config,
)


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
            status=SubmissionStatus.COMPLETED,
        )

        # Create an old event (95 days ago)
        old_time = datetime.utcnow() - timedelta(days=95)
        old_event = await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.CREATED,
            new_status=SubmissionStatus.PENDING,
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
            status=SubmissionStatus.COMPLETED,
        )

        # Create a recent event (1 day ago)
        recent_time = datetime.utcnow() - timedelta(days=1)
        recent_event = await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.CREATED,
            new_status=SubmissionStatus.PENDING,
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
        # Create a stale submission (8 days ago, stuck in processing - beyond 7 day threshold)
        stale_time = datetime.utcnow() - timedelta(days=8)
        stale_submission = await Submission.create(
            submission_id="stale-test",
            name="Stale Test",
            repo_url="https://github.com/test/stale",
            status=SubmissionStatus.CLONING,
        )
        # Manually update updated_at since auto_now=True overrides on create
        await Submission.filter(id=stale_submission.id).update(updated_at=stale_time)

        result = await cleanup_stale_submissions()

        assert result["updated"] >= 1

        # Verify status was updated
        await stale_submission.refresh_from_db()
        assert stale_submission.status == SubmissionStatus.FAILED
        assert "超时" in stale_submission.error_message

    @pytest.mark.asyncio
    async def test_cleanup_stale_keeps_recent(self, db):
        """Test that recent processing submissions are not marked stale - 边界值"""
        recent_submission = await Submission.create(
            submission_id="recent-processing",
            name="Recent Processing",
            repo_url="https://github.com/test/recent",
            status=SubmissionStatus.GENERATING,
        )

        result = await cleanup_stale_submissions()

        await recent_submission.refresh_from_db()
        assert recent_submission.status == SubmissionStatus.GENERATING

    @pytest.mark.asyncio
    async def test_cleanup_stale_ignores_other_statuses(self, db):
        """Test that non-processing statuses are not affected - 边界值"""
        stale_time = datetime.utcnow() - timedelta(days=2)
        other_submission = await Submission.create(
            submission_id="stale-other",
            name="Stale Other",
            repo_url="https://github.com/test/other",
            status=SubmissionStatus.COMPLETED,  # Not processing
        )
        await Submission.filter(id=other_submission.id).update(updated_at=stale_time)

        result = await cleanup_stale_submissions()

        await other_submission.refresh_from_db()
        assert other_submission.status == SubmissionStatus.COMPLETED


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
            status=SubmissionStatus.COMPLETED,
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

        assert cleanup_old_events in config
        assert cleanup_stale_submissions in config
        assert generate_daily_stats in config

        # Check config format
        for task_func, (interval, description) in config.items():
            assert isinstance(interval, int)
            assert isinstance(description, str)
            assert interval > 0
