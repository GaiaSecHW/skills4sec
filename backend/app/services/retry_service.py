"""
提交重试服务 - Issue 创建失败自动重试机制
"""
import uuid
import httpx
from datetime import datetime, timedelta
from typing import Optional, Tuple

from app.models.submission import (
    Submission,
    SubmissionEvent,
    SubmissionStatus,
    SubmissionEventType
)
from app.config import settings
from app.core.harness_logging import HarnessLogger
from app.utils import build_issue_body

logger = HarnessLogger("retry")


class RetryConfig:
    """重试配置"""
    # 重试延迟(秒): 第1次30s, 第2次60s, 第3次120s
    RETRY_DELAYS = [30, 60, 120]
    # 最大重试次数
    MAX_RETRIES = 3
    # 请求超时
    REQUEST_TIMEOUT = 30.0


class RetryService:
    """提交重试服务"""

    def __init__(self):
        self.gitea_api_url = settings.GITEA_API_URL
        self.gitea_token = settings.GITEA_TOKEN
        self.gitea_repo = settings.GITEA_REPO

    async def schedule_retry(
        self,
        submission: Submission,
        error_message: Optional[str] = None
    ) -> bool:
        """
        安排下次重试

        Args:
            submission: 提交记录
            error_message: 错误信息

        Returns:
            是否成功安排重试
        """
        if submission.retry_count >= submission.max_retries:
            logger.warning(
    "重试次数已达上限",
    event="max_retries_reached",
    business={"submission_id": submission.submission_id, "retry_count": submission.retry_count, "max_retries": submission.max_retries},
)
            return False

        # 计算延迟时间
        delays = RetryConfig.RETRY_DELAYS
        delay_index = min(submission.retry_count, len(delays) - 1)
        delay_seconds = delays[delay_index]

        submission.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
        submission.error_message = error_message

        await submission.save()

        # 记录事件
        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.RETRY_SCHEDULED,
            old_status=submission.status,
            new_status=submission.status,
            message=f"已安排第 {submission.retry_count + 1} 次重试，将在 {delay_seconds} 秒后执行",
            details={
                "retry_count": submission.retry_count + 1,
                "delay_seconds": delay_seconds,
                "next_retry_at": submission.next_retry_at.isoformat()
            },
            triggered_by="system"
        )

        logger.info(
            "重试已安排",
            event="retry_scheduled",
            business={"submission_id": submission.submission_id, "retry_count": submission.retry_count + 1, "delay_seconds": delay_seconds},
        )
        return True

    async def execute_retry(self, submission: Submission) -> Tuple[bool, str]:
        """
        执行重试 - 重新创建 Issue

        Args:
            submission: 提交记录

        Returns:
            (是否成功, 消息)
        """
        logger.info(
            "开始执行重试",
            event="retry_executing",
            business={"submission_id": submission.submission_id},
        )

        # 更新状态
        old_status = submission.status
        submission.status = SubmissionStatus.CREATING_ISSUE
        submission.last_retry_at = datetime.utcnow()
        await submission.save()

        # 记录事件
        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.CREATING_ISSUE,
            old_status=old_status,
            new_status=SubmissionStatus.CREATING_ISSUE,
            message=f"正在执行第 {submission.retry_count + 1} 次重试",
            details={"retry_count": submission.retry_count + 1},
            triggered_by="system"
        )

        try:
            success, message, issue_data = await self._create_gitea_issue(submission)

            if success:
                # 成功
                submission.status = SubmissionStatus.ISSUE_CREATED
                submission.issue_number = issue_data.get("number")
                submission.issue_url = issue_data.get("html_url")
                submission.issue_created_at = datetime.utcnow()
                submission.retry_count += 1
                submission.next_retry_at = None
                submission.error_message = None
                submission.error_code = None
                await submission.save()

                await SubmissionEvent.create(
                    submission=submission,
                    event_type=SubmissionEventType.RETRY_SUCCESS,
                    old_status=old_status,
                    new_status=SubmissionStatus.ISSUE_CREATED,
                    message=f"重试成功，Issue #{submission.issue_number} 已创建",
                    details={
                        "issue_number": submission.issue_number,
                        "issue_url": submission.issue_url,
                        "retry_count": submission.retry_count
                    },
                    triggered_by="system"
                )

                logger.info(
            "重试成功",
            event="retry_success",
            business={"submission_id": submission.submission_id, "issue_number": submission.issue_number, "retry_count": submission.retry_count},
        )
                return True, "Issue 创建成功"

            else:
                # 失败
                submission.retry_count += 1
                can_retry = await self.schedule_retry(submission, message)

                if not can_retry:
                    # 达到最大重试次数
                    submission.status = SubmissionStatus.ISSUE_FAILED
                    submission.error_message = f"重试 {submission.retry_count} 次后仍然失败: {message}"
                    await submission.save()

                    await SubmissionEvent.create(
                        submission=submission,
                        event_type=SubmissionEventType.RETRY_FAILED,
                        old_status=old_status,
                        new_status=SubmissionStatus.ISSUE_FAILED,
                        message=f"重试失败，已达到最大重试次数 ({submission.max_retries})",
                        details={
                            "retry_count": submission.retry_count,
                            "max_retries": submission.max_retries,
                            "error": message
                        },
                        error_message=message,
                        triggered_by="system"
                    )

                    logger.warning(
                        "重试失败，已达最大重试次数",
                        event="retry_max_retries_reached",
                        business={"submission_id": submission.submission_id, "retry_count": submission.retry_count, "max_retries": submission.max_retries},
                    )
                    return False, f"重试 {submission.retry_count} 次后仍然失败"

                await submission.save()
                return False, f"重试失败，已安排下次重试: {message}"

        except Exception as e:
            logger.exception(
                    "重试异常",
                    event="retry_exception",
                    error=e,
                    business={"submission_id": submission.submission_id},
                )
            submission.retry_count += 1
            await self.schedule_retry(submission, str(e))
            return False, f"重试异常: {str(e)}"

    async def _create_gitea_issue(
        self,
        submission: Submission
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        调用 Gitea API 创建 Issue

        Returns:
            (是否成功, 消息, Issue数据)
        """
        if not self.gitea_token:
            return False, "Gitea Token 未配置", None

        body = build_issue_body(submission)

        async with httpx.AsyncClient(
            timeout=RetryConfig.REQUEST_TIMEOUT,
            trust_env=False
        ) as client:
            try:
                response = await client.post(
                    f"{self.gitea_api_url}/repos/{self.gitea_repo}/issues",
                    headers={
                        "Authorization": f"token {self.gitea_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "title": f"[技能提交] {submission.name}",
                        "body": body,
                    }
                )

                if response.status_code == 201:
                    data = response.json()

                    # 添加 pending-approval 标签
                    if data.get("number"):
                        try:
                            await client.post(
                                f"{self.gitea_api_url}/repos/{self.gitea_repo}/issues/{data['number']}/labels",
                                headers={
                                    "Authorization": f"token {self.gitea_token}",
                                    "Content-Type": "application/json",
                                },
                                json={"labels": [1]}  # pending-approval label ID
                            )
                        except Exception:
                            pass  # 标签添加失败不影响主流程

                    return True, "Issue 创建成功", data

                else:
                    error_detail = response.text[:500]
                    return False, f"Gitea API 错误 ({response.status_code}): {error_detail}", None

            except httpx.TimeoutException:
                return False, "请求 Gitea API 超时", None
            except httpx.RequestError as e:
                return False, f"网络错误: {str(e)}", None

    async def process_pending_retries(self) -> dict:
        """
        处理所有待重试的提交 (定时任务调用)

        Returns:
            处理结果统计
        """
        now = datetime.utcnow()
        pending_submissions = await Submission.filter(
            status=SubmissionStatus.ISSUE_FAILED,
            next_retry_at__lte=now
        ).all()

        results = {
            "total": len(pending_submissions),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "details": []
        }

        for submission in pending_submissions:
            try:
                success, message = await self.execute_retry(submission)
                if success:
                    results["success"] += 1
                else:
                    results["failed"] += 1

                results["details"].append({
                    "submission_id": submission.submission_id,
                    "name": submission.name,
                    "success": success,
                    "message": message
                })

            except Exception as e:
                results["skipped"] += 1
                logger.exception(
                    "处理重试时发生错误",
                    event="retry_processing_error",
                    error=e,
                    business={"submission_id": submission.submission_id},
                )
                results["details"].append({
                    "submission_id": submission.submission_id,
                    "name": submission.name,
                    "success": False,
                    "message": str(e)
                })

        logger.info(
            "批量重试处理完成",
            event="pending_retries_processed",
            business={"total": results["total"], "success": results["success"], "failed": results["failed"], "skipped": results["skipped"]},
        )
        return results

    async def manual_retry(self, submission: Submission) -> Tuple[bool, str]:
        """
        手动触发重试 (管理员操作)

        Args:
            submission: 提交记录

        Returns:
            (是否成功, 消息)
        """
        if not submission.is_retryable:
            return False, f"当前状态 {submission.status} 不支持重试"

        # 重置重试计数，允许额外重试
        if submission.retry_count >= submission.max_retries:
            submission.retry_count = 0

        return await self.execute_retry(submission)


# 单例
retry_service = RetryService()
