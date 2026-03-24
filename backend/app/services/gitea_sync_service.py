"""
Gitea 状态同步服务 - 从 Gitea 同步 Issue/PR 状态
"""
import httpx
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from app.models.submission import (
    Submission,
    SubmissionEvent,
    SubmissionStatus,
    SubmissionEventType
)
from app.config import settings

logger = logging.getLogger(__name__)


class WorkflowRunStatus:
    """工作流运行状态常量"""
    PENDING = "pending"
    WAITING = "waiting"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        """是否为终态"""
        return status in (cls.SUCCESS, cls.FAILURE, cls.CANCELLED, cls.SKIPPED)

    @classmethod
    def is_success(cls, status: str) -> bool:
        """是否成功"""
        return status == cls.SUCCESS


class GiteaSyncService:
    """Gitea 状态同步服务"""

    def __init__(self):
        self.api_url = settings.GITEA_API_URL
        self.token = settings.GITEA_TOKEN
        self.repo = settings.GITEA_REPO

    async def get_issue(self, issue_number: int) -> Optional[Dict[str, Any]]:
        """获取 Issue 详情"""
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.api_url}/repos/{self.repo}/issues/{issue_number}",
                    headers={
                        "Authorization": f"token {self.token}",
                    }
                )
                if response.status_code == 200:
                    return response.json()
                return None
            except Exception as e:
                logger.error(f"Failed to get issue #{issue_number}: {e}")
                return None

    async def get_pr(self, pr_number: int) -> Optional[Dict[str, Any]]:
        """获取 PR 详情"""
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.api_url}/repos/{self.repo}/pulls/{pr_number}",
                    headers={
                        "Authorization": f"token {self.token}",
                    }
                )
                if response.status_code == 200:
                    return response.json()
                return None
            except Exception as e:
                logger.error(f"Failed to get PR #{pr_number}: {e}")
                return None

    async def get_issue_comments(self, issue_number: int) -> List[Dict[str, Any]]:
        """获取 Issue 评论"""
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.api_url}/repos/{self.repo}/issues/{issue_number}/comments",
                    headers={
                        "Authorization": f"token {self.token}",
                    }
                )
                if response.status_code == 200:
                    return response.json()
                return []
            except Exception as e:
                logger.error(f"Failed to get issue #{issue_number} comments: {e}")
                return []

    async def sync_submission(self, submission: Submission) -> bool:
        """
        同步单个提交的状态

        Returns:
            是否有状态变更
        """
        if not submission.issue_number:
            return False

        changed = False
        old_status = submission.status

        # 同步 Issue 状态
        issue = await self.get_issue(submission.issue_number)
        if issue:
            changed = await self._sync_issue_status(submission, issue)

        # 同步 PR 状态
        if submission.pr_number:
            pr = await self.get_pr(submission.pr_number)
            if pr:
                changed = await self._sync_pr_status(submission, pr) or changed

        # 同步工作流运行状态
        if submission.status == SubmissionStatus.PROCESSING:
            workflow_changed, _ = await self.sync_workflow_run_status(submission)
            changed = workflow_changed or changed

        # 检查审批/拒绝命令
        if submission.status == SubmissionStatus.ISSUE_CREATED:
            changed = await self._check_approval_commands(submission) or changed

        if changed:
            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.STATUS_SYNCED,
                old_status=old_status,
                new_status=submission.status,
                message="状态从 Gitea 同步",
                triggered_by="scheduler"
            )
            await submission.save()

        return changed

    async def _sync_issue_status(
        self,
        submission: Submission,
        issue: Dict[str, Any]
    ) -> bool:
        """同步 Issue 状态"""
        changed = False

        # 更新 Issue 基本状态
        new_state = issue.get("state")
        if new_state != submission.issue_state:
            submission.issue_state = new_state
            changed = True

        # 更新标签
        labels = [l.get("name") for l in issue.get("labels", [])]
        if labels != submission.issue_labels:
            submission.issue_labels = labels
            changed = True

        # 如果 Issue 被关闭
        if new_state == "closed" and not submission.is_terminal:
            submission.status = SubmissionStatus.CLOSED
            submission.completed_at = datetime.utcnow()
            changed = True

        return changed

    async def _sync_pr_status(
        self,
        submission: Submission,
        pr: Dict[str, Any]
    ) -> bool:
        """同步 PR 状态"""
        changed = False

        # 更新 PR 基本状态
        new_state = pr.get("state")
        if new_state != submission.pr_state:
            submission.pr_state = new_state
            changed = True

        # 检查是否合并
        merged = pr.get("merged", False)
        if merged and not submission.pr_merged:
            submission.pr_merged = True
            submission.status = SubmissionStatus.MERGED
            submission.completed_at = datetime.utcnow()
            changed = True

        return changed

    async def _check_approval_commands(self, submission: Submission) -> bool:
        """检查 Issue 中的审批/拒绝命令"""
        comments = await self.get_issue_comments(submission.issue_number)
        if not comments:
            return False

        # 获取上次检查后的评论
        last_check = submission.updated_at
        new_comments = [
            c for c in comments
            if datetime.fromisoformat(c["created_at"].replace("Z", "+00:00")) > last_check
        ]

        for comment in reversed(new_comments):  # 从最新开始
            body = comment.get("body", "").strip()
            username = comment.get("user", {}).get("login", "")

            # 检查审批命令
            if body.startswith("/approve"):
                # 验证权限 (这里简化处理，实际应该检查用户权限)
                submission.status = SubmissionStatus.APPROVED
                submission.approved_by_employee_id = username
                submission.approved_at = datetime.utcnow()

                await SubmissionEvent.create(
                    submission=submission,
                    event_type=SubmissionEventType.APPROVED,
                    old_status=SubmissionStatus.ISSUE_CREATED,
                    new_status=SubmissionStatus.APPROVED,
                    message=f"通过 Issue 评论审批",
                    details={
                        "approver": username,
                        "comment_id": comment.get("id"),
                        "issue_number": submission.issue_number
                    },
                    actor_employee_id=username,
                    triggered_by="user"
                )
                return True

            # 检查拒绝命令
            elif body.startswith("/reject"):
                reason = body[7:].strip() or "未提供原因"
                submission.status = SubmissionStatus.REJECTED
                submission.rejected_by_employee_id = username
                submission.rejected_at = datetime.utcnow()
                submission.reject_reason = reason

                await SubmissionEvent.create(
                    submission=submission,
                    event_type=SubmissionEventType.REJECTED,
                    old_status=SubmissionStatus.ISSUE_CREATED,
                    new_status=SubmissionStatus.REJECTED,
                    message=f"通过 Issue 评论拒绝: {reason}",
                    details={
                        "rejector": username,
                        "reason": reason,
                        "comment_id": comment.get("id"),
                        "issue_number": submission.issue_number
                    },
                    actor_employee_id=username,
                    triggered_by="user"
                )
                return True

        return False

    async def sync_all_pending(self) -> Dict[str, int]:
        """
        同步所有待处理的提交 (定时任务调用)

        Returns:
            同步结果统计
        """
        results = {
            "total": 0,
            "updated": 0,
            "errors": 0
        }

        # 获取需要同步的提交
        # 包括: issue_created, approved, processing, pr_created
        sync_statuses = [
            SubmissionStatus.ISSUE_CREATED,
            SubmissionStatus.APPROVED,
            SubmissionStatus.PROCESSING,
            SubmissionStatus.PR_CREATED,
        ]

        submissions = await Submission.filter(
            status__in=sync_statuses,
            issue_number__isnull=False
        ).all()

        results["total"] = len(submissions)

        for submission in submissions:
            try:
                changed = await self.sync_submission(submission)
                if changed:
                    results["updated"] += 1
            except Exception as e:
                results["errors"] += 1
                logger.exception(f"Error syncing submission {submission.submission_id}")

        logger.info(
            f"Gitea sync completed: {results['total']} checked, "
            f"{results['updated']} updated, {results['errors']} errors"
        )
        return results

    async def trigger_workflow(
        self,
        submission: Submission,
        workflow_name: str = "submission.yml"
    ) -> Tuple[bool, str, Optional[str]]:
        """
        触发 Gitea Actions 工作流

        Returns:
            (是否成功, 消息, Run ID)
        """
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            try:
                response = await client.post(
                    f"{self.api_url}/repos/{self.repo}/actions/workflows/{workflow_name}/dispatches",
                    headers={
                        "Authorization": f"token {self.token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "ref": "main",
                        "inputs": {
                            "submission_id": submission.submission_id,
                            "source_url": submission.repo_url,
                        }
                    }
                )

                if response.status_code in (200, 204):
                    # 更新状态
                    old_status = submission.status
                    submission.status = SubmissionStatus.PROCESSING
                    submission.processing_started_at = datetime.utcnow()
                    await submission.save()

                    await SubmissionEvent.create(
                        submission=submission,
                        event_type=SubmissionEventType.PROCESSING_STARTED,
                        old_status=old_status,
                        new_status=SubmissionStatus.PROCESSING,
                        message="已触发处理工作流",
                        details={
                            "workflow_name": workflow_name,
                            "submission_id": submission.submission_id
                        },
                        triggered_by="system"
                    )

                    return True, "工作流已触发", None
                else:
                    error = response.text[:200]
                    return False, f"触发失败: {error}", None

            except Exception as e:
                logger.exception(f"Failed to trigger workflow for {submission.submission_id}")
                return False, str(e), None

    async def add_issue_comment(
        self,
        issue_number: int,
        body: str
    ) -> bool:
        """添加 Issue 评论"""
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            try:
                response = await client.post(
                    f"{self.api_url}/repos/{self.repo}/issues/{issue_number}/comments",
                    headers={
                        "Authorization": f"token {self.token}",
                        "Content-Type": "application/json",
                    },
                    json={"body": body}
                )
                return response.status_code == 201
            except Exception as e:
                logger.error(f"Failed to add comment to issue #{issue_number}: {e}")
                return False

    async def close_issue(
        self,
        issue_number: int,
        reason: str = ""
    ) -> bool:
        """关闭 Issue"""
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            try:
                # 先添加评论
                if reason:
                    await self.add_issue_comment(issue_number, f"❌ **关闭原因**: {reason}")

                # 关闭 Issue
                response = await client.patch(
                    f"{self.api_url}/repos/{self.repo}/issues/{issue_number}",
                    headers={
                        "Authorization": f"token {self.token}",
                        "Content-Type": "application/json",
                    },
                    json={"state": "closed"}
                )
                return response.status_code == 200
            except Exception as e:
                logger.error(f"Failed to close issue #{issue_number}: {e}")
                return False

    # ============ Gitea Actions Workflow Runs API ============

    async def list_workflow_runs(
        self,
        workflow_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取工作流运行列表

        Args:
            workflow_name: 可选，按工作流名称筛选
            status: 可选，按状态筛选 (pending, running, success, failure, etc.)
            limit: 返回数量限制

        Returns:
            工作流运行列表
        """
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            try:
                params = {"limit": limit}
                if status:
                    params["status"] = status

                response = await client.get(
                    f"{self.api_url}/repos/{self.repo}/actions/runs",
                    headers={"Authorization": f"token {self.token}"},
                    params=params
                )
                if response.status_code == 200:
                    data = response.json()
                    runs = data.get("workflow_runs", [])

                    # 按工作流名称筛选
                    if workflow_name:
                        runs = [
                            r for r in runs
                            if r.get("name") == workflow_name or
                            workflow_name in r.get("path", "")
                        ]
                    return runs
                return []
            except Exception as e:
                logger.error(f"Failed to list workflow runs: {e}")
                return []

    async def get_workflow_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        """
        获取单个工作流运行详情

        Args:
            run_id: 工作流运行 ID

        Returns:
            工作流运行详情，失败返回 None
        """
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.api_url}/repos/{self.repo}/actions/runs/{run_id}",
                    headers={"Authorization": f"token {self.token}"}
                )
                if response.status_code == 200:
                    return response.json()
                return None
            except Exception as e:
                logger.error(f"Failed to get workflow run {run_id}: {e}")
                return None

    async def get_workflow_run_jobs(
        self,
        run_id: int
    ) -> List[Dict[str, Any]]:
        """
        获取工作流运行的任务列表

        Args:
            run_id: 工作流运行 ID

        Returns:
            任务列表
        """
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.api_url}/repos/{self.repo}/actions/runs/{run_id}/jobs",
                    headers={"Authorization": f"token {self.token}"}
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("jobs", [])
                return []
            except Exception as e:
                logger.error(f"Failed to get workflow run {run_id} jobs: {e}")
                return []

    async def find_workflow_run_by_submission(
        self,
        submission_id: str,
        limit: int = 20
    ) -> Optional[Dict[str, Any]]:
        """
        根据提交 ID 查找工作流运行

        Args:
            submission_id: 提交 UUID
            limit: 搜索范围

        Returns:
            最新的匹配工作流运行，未找到返回 None
        """
        runs = await self.list_workflow_runs(limit=limit)
        for run in runs:
            # 检查工作流输入参数中的 submission_id
            inputs = run.get("inputs", {}) or {}
            if inputs.get("submission_id") == submission_id:
                return run

            # 检查触发事件的 display_title 或 message
            display_title = run.get("display_title", "") or ""
            if submission_id in display_title:
                return run

        return None

    async def sync_workflow_run_status(
        self,
        submission: Submission
    ) -> Tuple[bool, Optional[str]]:
        """
        同步工作流运行状态

        Args:
            submission: 提交记录

        Returns:
            (是否有变更, 新状态描述)
        """
        if submission.status != SubmissionStatus.PROCESSING:
            return False, None

        # 优先使用已记录的 run_id
        run = None
        if submission.workflow_run_id:
            run = await self.get_workflow_run(int(submission.workflow_run_id))

        # 如果没有 run_id，尝试通过 submission_id 查找
        if not run:
            run = await self.find_workflow_run_by_submission(submission.submission_id)

        if not run:
            return False, None

        # 更新工作流信息
        changed = False
        run_id = str(run.get("id"))
        run_status = run.get("status", "")
        run_conclusion = run.get("conclusion") or ""
        run_url = run.get("html_url", "")

        # 更新 run_id 和 url
        if run_id and run_id != submission.workflow_run_id:
            submission.workflow_run_id = run_id
            submission.workflow_run_url = run_url
            changed = True

        # 处理工作流状态
        if WorkflowRunStatus.is_terminal(run_status):
            if WorkflowRunStatus.is_success(run_status) or run_conclusion == "success":
                # 工作流成功完成，等待 PR 创建
                submission.status = SubmissionStatus.PR_CREATED
                submission.processing_completed_at = datetime.utcnow()
                changed = True

                await SubmissionEvent.create(
                    submission=submission,
                    event_type=SubmissionEventType.PROCESSING_SUCCESS,
                    old_status=SubmissionStatus.PROCESSING,
                    new_status=SubmissionStatus.PR_CREATED,
                    message="工作流执行成功",
                    details={
                        "run_id": run_id,
                        "run_status": run_status,
                        "run_url": run_url
                    },
                    triggered_by="scheduler"
                )
            else:
                # 工作流失败
                submission.status = SubmissionStatus.PROCESS_FAILED
                submission.error_message = f"工作流执行失败: {run_conclusion or run_status}"
                submission.processing_completed_at = datetime.utcnow()
                changed = True

                await SubmissionEvent.create(
                    submission=submission,
                    event_type=SubmissionEventType.PROCESSING_FAILED,
                    old_status=SubmissionStatus.PROCESSING,
                    new_status=SubmissionStatus.PROCESS_FAILED,
                    message=f"工作流执行失败: {run_conclusion or run_status}",
                    details={
                        "run_id": run_id,
                        "run_status": run_status,
                        "run_conclusion": run_conclusion,
                        "run_url": run_url
                    },
                    triggered_by="scheduler"
                )

        if changed:
            await submission.save()

        return changed, run_status

    async def get_workflow_progress(
        self,
        submission: Submission
    ) -> Dict[str, Any]:
        """
        获取工作流进度详情（用于前端展示）

        Args:
            submission: 提交记录

        Returns:
            工作流进度信息
        """
        result = {
            "has_workflow": False,
            "run_id": None,
            "status": None,
            "conclusion": None,
            "started_at": None,
            "completed_at": None,
            "duration_seconds": None,
            "url": None,
            "jobs": []
        }

        # 获取工作流运行信息
        run = None
        if submission.workflow_run_id:
            run = await self.get_workflow_run(int(submission.workflow_run_id))

        if not run:
            run = await self.find_workflow_run_by_submission(submission.submission_id)

        if not run:
            return result

        result["has_workflow"] = True
        result["run_id"] = str(run.get("id"))
        result["status"] = run.get("status")
        result["conclusion"] = run.get("conclusion")
        result["url"] = run.get("html_url")

        # 解析时间
        started_at = run.get("started_at") or run.get("run_started_at")
        if started_at:
            result["started_at"] = started_at
            try:
                start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            except Exception:
                start_time = None
        else:
            start_time = None

        completed_at = run.get("completed_at") or run.get("updated_at")
        if completed_at and WorkflowRunStatus.is_terminal(run.get("status", "")):
            result["completed_at"] = completed_at
            try:
                end_time = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
            except Exception:
                end_time = None
        else:
            end_time = None

        # 计算持续时间
        if start_time:
            if end_time:
                result["duration_seconds"] = int((end_time - start_time).total_seconds())
            elif run.get("status") == "running":
                result["duration_seconds"] = int((datetime.utcnow() - start_time.replace(tzinfo=None)).total_seconds())

        # 获取任务列表
        if run.get("id"):
            jobs = await self.get_workflow_run_jobs(run["id"])
            result["jobs"] = [
                {
                    "id": job.get("id"),
                    "name": job.get("name"),
                    "status": job.get("status"),
                    "conclusion": job.get("conclusion"),
                    "started_at": job.get("started_at"),
                    "completed_at": job.get("completed_at"),
                }
                for job in jobs
            ]

        return result


# 单例
gitea_sync_service = GiteaSyncService()
