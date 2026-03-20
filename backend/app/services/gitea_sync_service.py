"""
Gitea 状态同步服务 - 从 Gitea 同步 Issue/PR 状态
"""
import httpx
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.models.submission import (
    Submission,
    SubmissionEvent,
    SubmissionStatus,
    SubmissionEventType
)
from app.config import settings

logger = logging.getLogger(__name__)


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


# 需要导入 Tuple
from typing import Tuple

# 单例
gitea_sync_service = GiteaSyncService()
