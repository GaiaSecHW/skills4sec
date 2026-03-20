"""
技能提交模型 - 工作流监控和重试机制
"""
from enum import Enum
from tortoise import fields
from tortoise.models import Model
from datetime import datetime
from typing import Optional


class SubmissionStatus(str, Enum):
    """提交状态枚举"""
    # 初始阶段
    PENDING = "pending"              # 待处理
    CREATING_ISSUE = "creating_issue"  # 正在创建Issue

    # Issue 阶段
    ISSUE_CREATED = "issue_created"   # Issue已创建，等待审批
    ISSUE_FAILED = "issue_failed"     # Issue创建失败
    APPROVED = "approved"             # 已审批通过
    REJECTED = "rejected"             # 已拒绝

    # 处理阶段
    PROCESSING = "processing"         # 正在处理
    PROCESS_FAILED = "process_failed" # 处理失败

    # 完成阶段
    PR_CREATED = "pr_created"         # PR已创建
    MERGED = "merged"                 # 已合并
    CLOSED = "closed"                 # 已关闭


class SubmissionEventType(str, Enum):
    """提交事件类型枚举"""
    # 创建阶段
    CREATED = "created"
    CREATING_ISSUE = "creating_issue"
    ISSUE_CREATE_SUCCESS = "issue_create_success"
    ISSUE_CREATE_FAILED = "issue_create_failed"
    RETRY_SCHEDULED = "retry_scheduled"
    RETRY_SUCCESS = "retry_success"
    RETRY_FAILED = "retry_failed"

    # 审批阶段
    APPROVED = "approved"
    REJECTED = "rejected"

    # 处理阶段
    PROCESSING_STARTED = "processing_started"
    PROCESSING_PROGRESS = "processing_progress"
    PROCESSING_SUCCESS = "processing_success"
    PROCESSING_FAILED = "processing_failed"

    # 完成阶段
    PR_CREATED = "pr_created"
    MERGED = "merged"
    CLOSED = "closed"

    # 状态同步
    STATUS_SYNCED = "status_synced"
    MANUAL_OVERRIDE = "manual_override"


class Submission(Model):
    """技能提交记录"""
    id = fields.IntField(pk=True)

    # 基本信息
    submission_id = fields.CharField(max_length=36, unique=True, index=True, description="UUID")
    name = fields.CharField(max_length=200, description="技能名称")
    repo_url = fields.CharField(max_length=500, description="仓库地址")
    description = fields.TextField(null=True, description="描述")
    category = fields.CharField(max_length=50, null=True, description="分类")
    contact = fields.CharField(max_length=200, null=True, description="联系方式")

    # 提交者信息
    submitter_id = fields.IntField(null=True, description="提交用户ID")
    submitter_employee_id = fields.CharField(max_length=20, null=True, description="提交者工号")
    submitter_ip = fields.CharField(max_length=45, null=True, description="提交者IP")
    submitter_user_agent = fields.CharField(max_length=500, null=True, description="User Agent")

    # 状态流转
    status = fields.CharEnumField(
        SubmissionStatus,
        default=SubmissionStatus.PENDING,
        description="当前状态"
    )

    # Gitea Issue 相关
    issue_number = fields.IntField(null=True, description="Gitea Issue 编号")
    issue_url = fields.CharField(max_length=500, null=True, description="Issue 链接")
    issue_state = fields.CharField(max_length=20, null=True, description="Issue 状态")
    issue_labels = fields.JSONField(null=True, description="Issue 标签")

    # PR 相关
    pr_number = fields.IntField(null=True, description="PR 编号")
    pr_url = fields.CharField(max_length=500, null=True, description="PR 链接")
    pr_state = fields.CharField(max_length=20, null=True, description="PR 状态")
    pr_merged = fields.BooleanField(default=False, description="PR 是否已合并")

    # 处理结果
    skill_count = fields.IntField(default=0, description="发现的技能数")
    processed_skills = fields.IntField(default=0, description="处理成功的技能数")
    failed_skills = fields.IntField(default=0, description="处理失败的技能数")
    skill_slugs = fields.JSONField(null=True, description="技能slug列表")
    highest_risk = fields.CharField(max_length=20, null=True, description="最高风险等级")
    workflow_run_id = fields.CharField(max_length=50, null=True, description="Gitea Actions Run ID")
    workflow_run_url = fields.CharField(max_length=500, null=True, description="Workflow 链接")

    # 重试机制
    retry_count = fields.IntField(default=0, description="已重试次数")
    max_retries = fields.IntField(default=3, description="最大重试次数")
    next_retry_at = fields.DatetimeField(null=True, description="下次重试时间")
    last_retry_at = fields.DatetimeField(null=True, description="上次重试时间")

    # 错误信息
    error_code = fields.CharField(max_length=50, null=True, description="错误代码")
    error_message = fields.TextField(null=True, description="错误信息")
    error_details = fields.JSONField(null=True, description="错误详情")

    # 审批信息
    approved_by = fields.IntField(null=True, description="审批人ID")
    approved_by_employee_id = fields.CharField(max_length=20, null=True, description="审批人工号")
    approved_at = fields.DatetimeField(null=True, description="审批时间")
    rejected_by = fields.IntField(null=True, description="拒绝人ID")
    rejected_by_employee_id = fields.CharField(max_length=20, null=True, description="拒绝人工号")
    rejected_at = fields.DatetimeField(null=True, description="拒绝时间")
    reject_reason = fields.TextField(null=True, description="拒绝原因")

    # 时间戳
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    issue_created_at = fields.DatetimeField(null=True, description="Issue创建时间")
    processing_started_at = fields.DatetimeField(null=True, description="处理开始时间")
    processing_completed_at = fields.DatetimeField(null=True, description="处理完成时间")
    completed_at = fields.DatetimeField(null=True, description="最终完成时间")

    class Meta:
        table = "submissions"
        indexes = [
            ("status",),
            ("submitter_employee_id",),
            ("created_at",),
            ("next_retry_at",),
        ]

    def __str__(self):
        return f"Submission({self.submission_id}, {self.name}, {self.status})"

    @property
    def is_retryable(self) -> bool:
        """是否可以重试"""
        return self.status in (
            SubmissionStatus.ISSUE_FAILED,
            SubmissionStatus.PROCESS_FAILED
        ) and self.retry_count < self.max_retries

    @property
    def is_terminal(self) -> bool:
        """是否已到达终态"""
        return self.status in (
            SubmissionStatus.MERGED,
            SubmissionStatus.CLOSED,
            SubmissionStatus.REJECTED
        )

    @property
    def duration_seconds(self) -> Optional[int]:
        """处理耗时(秒)"""
        if self.processing_started_at and self.processing_completed_at:
            delta = self.processing_completed_at - self.processing_started_at
            return int(delta.total_seconds())
        return None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "name": self.name,
            "repo_url": self.repo_url,
            "description": self.description,
            "category": self.category,
            "contact": self.contact,
            "submitter_employee_id": self.submitter_employee_id,
            "status": self.status.value if isinstance(self.status, SubmissionStatus) else self.status,
            "issue_number": self.issue_number,
            "issue_url": self.issue_url,
            "pr_number": self.pr_number,
            "pr_url": self.pr_url,
            "skill_count": self.skill_count,
            "processed_skills": self.processed_skills,
            "failed_skills": self.failed_skills,
            "highest_risk": self.highest_risk,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SubmissionEvent(Model):
    """提交事件日志 - 记录状态变更和处理过程"""
    id = fields.IntField(pk=True)

    submission = fields.ForeignKeyField(
        "models.Submission",
        related_name="events",
        description="关联的提交"
    )

    # 事件信息
    event_type = fields.CharEnumField(
        SubmissionEventType,
        description="事件类型"
    )
    old_status = fields.CharEnumField(
        SubmissionStatus,
        null=True,
        description="变更前状态"
    )
    new_status = fields.CharEnumField(
        SubmissionStatus,
        null=True,
        description="变更后状态"
    )

    # 事件内容
    message = fields.TextField(null=True, description="事件消息")
    details = fields.JSONField(null=True, description="详细信息")

    # 触发信息
    triggered_by = fields.CharField(max_length=50, null=True, description="触发源(system/user/scheduler)")
    actor_id = fields.IntField(null=True, description="操作人ID")
    actor_employee_id = fields.CharField(max_length=100, null=True, description="操作人工号")

    # 错误信息(如果有)
    error_code = fields.CharField(max_length=50, null=True, description="错误代码")
    error_message = fields.TextField(null=True, description="错误消息")

    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "submission_events"
        indexes = [
            ("submission_id", "created_at"),
            ("event_type",),
        ]

    def __str__(self):
        return f"SubmissionEvent({self.event_type}, {self.submission_id})"

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "event_type": self.event_type.value if isinstance(self.event_type, SubmissionEventType) else self.event_type,
            "old_status": self.old_status.value if self.old_status and isinstance(self.old_status, SubmissionStatus) else self.old_status,
            "new_status": self.new_status.value if self.new_status and isinstance(self.new_status, SubmissionStatus) else self.new_status,
            "message": self.message,
            "details": self.details,
            "triggered_by": self.triggered_by,
            "actor_employee_id": self.actor_employee_id,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
