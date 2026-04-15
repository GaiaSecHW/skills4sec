"""
重试服务 - 管理提交失败后的自动重试
"""
from datetime import datetime, timedelta
from typing import Tuple

from app.models.submission import (
    Submission,
    SubmissionEvent,
    SubmissionStatus,
    SubmissionEventType,
)
from app.core import get_logger

logger = get_logger("retry_service")

# 重试间隔（秒）：第1次60s，第2次300s，第3次900s
RETRY_DELAYS = [60, 300, 900]


class RetryService:
    """提交重试服务"""

    def _get_retry_delay(self, retry_count: int) -> int:
        """根据重试次数获取延迟秒数（指数退避）"""
        idx = min(retry_count, len(RETRY_DELAYS) - 1)
        return RETRY_DELAYS[idx]

    async def schedule_retry(
        self,
        submission: Submission,
        error_message: str,
    ) -> Tuple[bool, str]:
        """
        安排重试

        Args:
            submission: 提交记录
            error_message: 失败原因

        Returns:
            (是否已安排重试, 消息)
        """
        if submission.retry_count >= submission.max_retries:
            # 已达最大重试次数，标记为最终失败
            submission.status = SubmissionStatus.FAILED
            submission.error_message = f"已达到最大重试次数({submission.max_retries}): {error_message}"
            await submission.save()

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.RETRY_FAILED,
                old_status=submission.status,
                new_status=SubmissionStatus.FAILED,
                message=f"已达到最大重试次数({submission.max_retries})，不再重试",
                error_message=error_message,
                triggered_by="retry_service",
            )

            logger.warning(
                f"Submission {submission.submission_id} reached max retries ({submission.max_retries})",
            )
            return False, f"已达到最大重试次数({submission.max_retries})"

        # 增加重试计数
        submission.retry_count += 1
        delay = self._get_retry_delay(submission.retry_count - 1)
        submission.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
        submission.last_retry_at = datetime.utcnow()
        await submission.save()

        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.RETRY_SCHEDULED,
            old_status=submission.status,
            new_status=submission.status,
            message=f"已安排第 {submission.retry_count}/{submission.max_retries} 次重试，{delay}秒后执行",
            error_message=error_message,
            details={
                "retry_count": submission.retry_count,
                "max_retries": submission.max_retries,
                "delay_seconds": delay,
                "next_retry_at": submission.next_retry_at.isoformat(),
            },
            triggered_by="retry_service",
        )

        logger.info(
            f"Retry scheduled for submission {submission.submission_id}: "
            f"attempt {submission.retry_count}/{submission.max_retries} in {delay}s",
        )
        return True, f"已安排第 {submission.retry_count} 次重试，{delay}秒后执行"


# 单例
retry_service = RetryService()
