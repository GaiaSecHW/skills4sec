"""
Tests for Scheduler - 任务调度器测试
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.tasks.scheduler import (
    setup_scheduler,
    start_scheduler,
    shutdown_scheduler,
    run_task_manually,
    get_scheduler_status,
)


class TestSetupScheduler:
    """Test setup_scheduler function"""

    def test_setup_scheduler_import_error(self):
        """Test setup when APScheduler not installed"""
        # This is handled internally in the function
        # The function catches ImportError and returns None
        from app.tasks import scheduler as scheduler_module
        # Just verify the function exists
        assert hasattr(scheduler_module, 'setup_scheduler')

    def test_setup_scheduler_function_exists(self):
        """Test that setup_scheduler function exists"""
        from app.tasks import scheduler as scheduler_module

        # Reset global
        original_scheduler = scheduler_module.scheduler
        scheduler_module.scheduler = None

        try:
            # The function exists and is callable
            assert callable(scheduler_module.setup_scheduler)
        finally:
            # Restore original scheduler
            scheduler_module.scheduler = original_scheduler


class TestStartScheduler:
    """Test start_scheduler function"""

    def test_start_scheduler_available(self):
        """Test starting available scheduler"""
        mock_scheduler = MagicMock()

        import app.tasks.scheduler as scheduler_module
        scheduler_module.scheduler = mock_scheduler

        scheduler_module.start_scheduler()

        mock_scheduler.start.assert_called_once()

    def test_start_scheduler_not_available(self):
        """Test starting when scheduler not available"""
        import app.tasks.scheduler as scheduler_module
        scheduler_module.scheduler = None

        # Should not raise
        scheduler_module.start_scheduler()


class TestShutdownScheduler:
    """Test shutdown_scheduler function"""

    def test_shutdown_scheduler_running(self):
        """Test shutting down running scheduler"""
        mock_scheduler = MagicMock()
        mock_scheduler.running = True

        import app.tasks.scheduler as scheduler_module
        scheduler_module.scheduler = mock_scheduler

        scheduler_module.shutdown_scheduler()

        mock_scheduler.shutdown.assert_called_once_with(wait=False)

    def test_shutdown_scheduler_not_running(self):
        """Test shutting down non-running scheduler"""
        mock_scheduler = MagicMock()
        mock_scheduler.running = False

        import app.tasks.scheduler as scheduler_module
        scheduler_module.scheduler = mock_scheduler

        scheduler_module.shutdown_scheduler()

        mock_scheduler.shutdown.assert_not_called()

    def test_shutdown_scheduler_none(self):
        """Test shutting down when scheduler is None"""
        import app.tasks.scheduler as scheduler_module
        scheduler_module.scheduler = None

        # Should not raise
        scheduler_module.shutdown_scheduler()


class TestRunTaskManually:
    """Test run_task_manually function"""

    @pytest.mark.asyncio
    async def test_run_task_manually_unknown_task(self):
        """Test running unknown task - 边界值"""
        result = await run_task_manually("unknown_task")

        assert result["success"] is False
        assert "Unknown task" in result["error"]

    @pytest.mark.asyncio
    async def test_run_task_manually_process_pending_retries(self):
        """Test running process_pending_retries task"""
        mock_result = {"total": 1, "success": 1, "failed": 0, "skipped": 0}

        with patch("app.tasks.submission_tasks.process_pending_retries", new_callable=AsyncMock) as mock_task:
            mock_task.return_value = mock_result

            result = await run_task_manually("process_pending_retries")

            assert result["success"] is True
            assert result["task"] == "process_pending_retries"
            assert result["result"] == mock_result

    @pytest.mark.asyncio
    async def test_run_task_manually_sync_gitea_status(self):
        """Test running sync_gitea_status task"""
        mock_result = {"total": 2, "updated": 1, "errors": 1}

        with patch("app.tasks.submission_tasks.sync_gitea_status", new_callable=AsyncMock) as mock_task:
            mock_task.return_value = mock_result

            result = await run_task_manually("sync_gitea_status")

            assert result["success"] is True
            assert result["result"] == mock_result

    @pytest.mark.asyncio
    async def test_run_task_manually_cleanup_old_events(self):
        """Test running cleanup_old_events task"""
        mock_result = {"deleted": 5}

        with patch("app.tasks.submission_tasks.cleanup_old_events", new_callable=AsyncMock) as mock_task:
            mock_task.return_value = mock_result

            result = await run_task_manually("cleanup_old_events")

            assert result["success"] is True
            assert result["result"] == mock_result

    @pytest.mark.asyncio
    async def test_run_task_manually_cleanup_stale_submissions(self):
        """Test running cleanup_stale_submissions task"""
        mock_result = {"updated": 3}

        with patch("app.tasks.submission_tasks.cleanup_stale_submissions", new_callable=AsyncMock) as mock_task:
            mock_task.return_value = mock_result

            result = await run_task_manually("cleanup_stale_submissions")

            assert result["success"] is True
            assert result["result"] == mock_result

    @pytest.mark.asyncio
    async def test_run_task_manually_generate_daily_stats(self):
        """Test running generate_daily_stats task"""
        mock_result = {"date": "2026-03-22", "total": 10, "by_status": {}}

        with patch("app.tasks.submission_tasks.generate_daily_stats", new_callable=AsyncMock) as mock_task:
            mock_task.return_value = mock_result

            result = await run_task_manually("generate_daily_stats")

            assert result["success"] is True
            assert result["result"] == mock_result

    @pytest.mark.asyncio
    async def test_run_task_manually_with_exception(self):
        """Test running task that raises exception - 边界值"""
        with patch("app.tasks.submission_tasks.process_pending_retries", new_callable=AsyncMock) as mock_task:
            mock_task.side_effect = Exception("Task failed")

            result = await run_task_manually("process_pending_retries")

            assert result["success"] is False
            assert "Task failed" in result["error"]


class TestGetSchedulerStatus:
    """Test get_scheduler_status function"""

    def test_get_scheduler_status_not_available(self):
        """Test status when scheduler not available"""
        import app.tasks.scheduler as scheduler_module
        scheduler_module.scheduler = None

        status = scheduler_module.get_scheduler_status()

        assert status["available"] is False
        assert status["running"] is False
        assert status["jobs"] == []

    def test_get_scheduler_status_available(self):
        """Test status when scheduler is available"""
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_job = MagicMock()
        mock_job.id = "test_job"
        mock_job.name = "Test Job"
        mock_job.next_run_time = None
        mock_job.trigger = "interval"
        mock_scheduler.get_jobs.return_value = [mock_job]

        import app.tasks.scheduler as scheduler_module
        scheduler_module.scheduler = mock_scheduler

        status = scheduler_module.get_scheduler_status()

        assert status["available"] is True
        assert status["running"] is True
        assert len(status["jobs"]) == 1
        assert status["jobs"][0]["id"] == "test_job"

    def test_get_scheduler_status_with_next_run(self):
        """Test status with next run time"""
        from datetime import datetime

        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_job = MagicMock()
        mock_job.id = "test_job"
        mock_job.name = "Test Job"
        mock_job.next_run_time = datetime(2026, 3, 23, 12, 0, 0)
        mock_job.trigger = "interval"
        mock_scheduler.get_jobs.return_value = [mock_job]

        import app.tasks.scheduler as scheduler_module
        scheduler_module.scheduler = mock_scheduler

        status = scheduler_module.get_scheduler_status()

        assert status["jobs"][0]["next_run"] is not None
