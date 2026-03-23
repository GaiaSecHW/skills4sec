"""
提交 Repository - 提交数据访问
"""
from typing import Optional, List
from datetime import datetime

from app.core.base_repository import BaseRepository
from app.models.submission import Submission, SubmissionEvent, SubmissionStatus


class SubmissionRepository(BaseRepository[Submission]):
    """提交数据访问层"""

    model_class = Submission

    async def find_by_submission_id(self, submission_id: str) -> Optional[Submission]:
        """通过 submission_id 查找"""
        return await self.model_class.get_or_none(submission_id=submission_id)

    async def find_by_issue_number(self, issue_number: int) -> Optional[Submission]:
        """通过 Issue 编号查找"""
        return await self.model_class.get_or_none(issue_number=issue_number)

    async def find_pending_sync(self) -> List[Submission]:
        """获取需要同步状态的提交"""
        sync_statuses = [
            SubmissionStatus.ISSUE_CREATED,
            SubmissionStatus.APPROVED,
            SubmissionStatus.PROCESSING,
            SubmissionStatus.PR_CREATED,
        ]
        return await self.model_class.filter(
            status__in=sync_statuses,
            issue_number__isnull=False
        ).all()

    async def find_by_status(
        self,
        status: SubmissionStatus,
        skip: int = 0,
        limit: int = 100
    ) -> List[Submission]:
        """按状态获取提交"""
        return await self.model_class.filter(
            status=status
        ).offset(skip).limit(limit).order_by("-created_at")

    async def count_by_status(self, status: SubmissionStatus) -> int:
        """统计指定状态的提交数"""
        return await self.model_class.filter(status=status).count()

    async def update_status(
        self,
        submission: Submission,
        new_status: SubmissionStatus,
        **extra_fields
    ) -> None:
        """更新提交状态"""
        submission.status = new_status
        for field, value in extra_fields.items():
            setattr(submission, field, value)
        await submission.save()


class SubmissionEventRepository(BaseRepository[SubmissionEvent]):
    """提交事件数据访问层"""

    model_class = SubmissionEvent

    async def find_by_submission(
        self,
        submission: Submission,
        skip: int = 0,
        limit: int = 50
    ) -> List[SubmissionEvent]:
        """获取提交的事件列表"""
        return await self.model_class.filter(
            submission=submission
        ).offset(skip).limit(limit).order_by("-created_at")
