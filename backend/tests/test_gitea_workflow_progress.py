"""
Gitea 工作流进度功能测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.gitea_sync_service import (
    GiteaSyncService,
    WorkflowRunStatus,
    gitea_sync_service
)
from app.models.submission import Submission, SubmissionStatus, SubmissionEventType


class TestWorkflowRunStatus:
    """测试 WorkflowRunStatus 类"""

    def test_is_terminal_success(self):
        """测试终态判断 - 成功"""
        assert WorkflowRunStatus.is_terminal("success") is True

    def test_is_terminal_failure(self):
        """测试终态判断 - 失败"""
        assert WorkflowRunStatus.is_terminal("failure") is True

    def test_is_terminal_cancelled(self):
        """测试终态判断 - 取消"""
        assert WorkflowRunStatus.is_terminal("cancelled") is True

    def test_is_terminal_skipped(self):
        """测试终态判断 - 跳过"""
        assert WorkflowRunStatus.is_terminal("skipped") is True

    def test_is_terminal_running(self):
        """测试非终态判断 - 运行中"""
        assert WorkflowRunStatus.is_terminal("running") is False

    def test_is_terminal_pending(self):
        """测试非终态判断 - 等待中"""
        assert WorkflowRunStatus.is_terminal("pending") is False

    def test_is_success_true(self):
        """测试成功判断"""
        assert WorkflowRunStatus.is_success("success") is True

    def test_is_success_false(self):
        """测试非成功判断"""
        assert WorkflowRunStatus.is_success("failure") is False
        assert WorkflowRunStatus.is_success("running") is False


class TestListWorkflowRuns:
    """测试 list_workflow_runs 方法"""

    @pytest.mark.asyncio
    async def test_list_workflow_runs_success(self):
        """测试成功获取工作流运行列表"""
        service = GiteaSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "workflow_runs": [
                {"id": 1, "status": "success", "name": "CI"},
                {"id": 2, "status": "running", "name": "Build"}
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await service.list_workflow_runs()

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["status"] == "running"

    @pytest.mark.asyncio
    async def test_list_workflow_runs_with_filter(self):
        """测试按工作流名称筛选"""
        service = GiteaSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "workflow_runs": [
                {"id": 1, "status": "success", "name": "submission.yml", "path": ".gitea/workflows/submission.yml"},
                {"id": 2, "status": "running", "name": "CI", "path": ".gitea/workflows/ci.yml"}
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await service.list_workflow_runs(workflow_name="submission.yml")

        assert len(result) == 1
        assert result[0]["name"] == "submission.yml"

    @pytest.mark.asyncio
    async def test_list_workflow_runs_empty(self):
        """测试空列表"""
        service = GiteaSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"workflow_runs": []}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await service.list_workflow_runs()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_workflow_runs_error(self):
        """测试错误处理"""
        service = GiteaSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await service.list_workflow_runs()

        assert result == []


class TestGetWorkflowRun:
    """测试 get_workflow_run 方法"""

    @pytest.mark.asyncio
    async def test_get_workflow_run_success(self):
        """测试成功获取单个工作流运行"""
        service = GiteaSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 123,
            "status": "running",
            "conclusion": None,
            "html_url": "https://gitea.example.com/actions/runs/123"
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await service.get_workflow_run(123)

        assert result["id"] == 123
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_workflow_run_not_found(self):
        """测试工作流运行不存在"""
        service = GiteaSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await service.get_workflow_run(999)

        assert result is None


class TestGetWorkflowRunJobs:
    """测试 get_workflow_run_jobs 方法"""

    @pytest.mark.asyncio
    async def test_get_workflow_run_jobs_success(self):
        """测试成功获取任务列表"""
        service = GiteaSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jobs": [
                {"id": 1, "name": "build", "status": "success"},
                {"id": 2, "name": "test", "status": "running"}
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await service.get_workflow_run_jobs(123)

        assert len(result) == 2
        assert result[0]["name"] == "build"
        assert result[1]["status"] == "running"


class TestFindWorkflowRunBySubmission:
    """测试 find_workflow_run_by_submission 方法"""

    @pytest.mark.asyncio
    async def test_find_by_submission_id_in_inputs(self):
        """测试通过 inputs 中的 submission_id 查找"""
        service = GiteaSyncService()
        submission_id = "test-uuid-123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "workflow_runs": [
                {"id": 1, "status": "running", "inputs": {"submission_id": "other-uuid"}},
                {"id": 2, "status": "running", "inputs": {"submission_id": submission_id}}
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await service.find_workflow_run_by_submission(submission_id)

        assert result is not None
        assert result["id"] == 2

    @pytest.mark.asyncio
    async def test_find_by_submission_id_in_title(self):
        """测试通过 display_title 查找"""
        service = GiteaSyncService()
        submission_id = "test-uuid-456"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "workflow_runs": [
                {"id": 1, "status": "running", "inputs": {}, "display_title": "Processing test-uuid-456"}
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await service.find_workflow_run_by_submission(submission_id)

        assert result is not None
        assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_find_not_found(self):
        """测试未找到工作流运行"""
        service = GiteaSyncService()
        submission_id = "nonexistent-uuid"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"workflow_runs": []}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await service.find_workflow_run_by_submission(submission_id)

        assert result is None


class TestGetWorkflowProgress:
    """测试 get_workflow_progress 方法"""

    @pytest.mark.asyncio
    async def test_get_workflow_progress_no_run(self):
        """测试没有工作流运行时"""
        service = GiteaSyncService()
        submission = MagicMock()
        submission.workflow_run_id = None
        submission.submission_id = "test-uuid"

        with patch.object(service, "find_workflow_run_by_submission", AsyncMock(return_value=None)):
            result = await service.get_workflow_progress(submission)

        assert result["has_workflow"] is False

    @pytest.mark.asyncio
    async def test_get_workflow_progress_running(self):
        """测试运行中的工作流"""
        service = GiteaSyncService()
        submission = MagicMock()
        submission.workflow_run_id = "123"
        submission.submission_id = "test-uuid"

        mock_run = {
            "id": 123,
            "status": "running",
            "conclusion": None,
            "html_url": "https://gitea.example.com/actions/runs/123",
            "started_at": "2024-01-01T10:00:00Z"
        }

        with patch.object(service, "get_workflow_run", AsyncMock(return_value=mock_run)):
            with patch.object(service, "get_workflow_run_jobs", AsyncMock(return_value=[])):
                result = await service.get_workflow_progress(submission)

        assert result["has_workflow"] is True
        assert result["status"] == "running"
        assert result["url"] == "https://gitea.example.com/actions/runs/123"

    @pytest.mark.asyncio
    async def test_get_workflow_progress_with_jobs(self):
        """测试带任务列表的工作流"""
        service = GiteaSyncService()
        submission = MagicMock()
        submission.workflow_run_id = "123"
        submission.submission_id = "test-uuid"

        mock_run = {
            "id": 123,
            "status": "success",
            "conclusion": "success",
            "html_url": "https://gitea.example.com/actions/runs/123",
            "started_at": "2024-01-01T10:00:00Z",
            "completed_at": "2024-01-01T10:05:00Z"
        }

        mock_jobs = [
            {"id": 1, "name": "build", "status": "completed", "conclusion": "success"},
            {"id": 2, "name": "test", "status": "completed", "conclusion": "success"}
        ]

        with patch.object(service, "get_workflow_run", AsyncMock(return_value=mock_run)):
            with patch.object(service, "get_workflow_run_jobs", AsyncMock(return_value=mock_jobs)):
                result = await service.get_workflow_progress(submission)

        assert result["has_workflow"] is True
        assert len(result["jobs"]) == 2
        assert result["duration_seconds"] == 300  # 5 minutes
