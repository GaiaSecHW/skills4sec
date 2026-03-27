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
    PENDING = "pending"              # 待处理
    CREATING_ISSUE = "creating_issue"  # 创建 Issue 中
    ISSUE_CREATED = "issue_created"  # Issue 已创建
    ISSUE_FAILED = "issue_failed"      # Issue 创建失败
    CLONING = "cloning"              # 克隆中
    GENERATING = "generating"        # 生成报告中
    MIGRATING = "migrating"          # 迁移中
    APPROVED = "approved"            # 已批准
    REJECTED = "rejected"            # 已拒绝
    PROCESSING = "processing"        # 处理中
    PR_CREATED = "pr_created"        # PR 已创建
    COMPLETED = "completed"          # 已完成
    FAILED = "failed"                # 失败（含失败原因）


class SubmissionEventType(str, Enum):
    """提交事件类型枚举"""
    # 创建
    CREATED = "created"

    # Issue 步骤
    ISSUE_CREATE_SUCCESS = "issue_create_success"
    ISSUE_CREATE_FAILED = "issue_create_failed"

    # 克隆步骤
    CLONE_STARTED = "clone_started"
    CLONE_SUCCESS = "clone_success"
    CLONE_FAILED = "clone_failed"

    # 生成步骤
    GENERATE_STARTED = "generate_started"
    GENERATE_SUCCESS = "generate_success"
    GENERATE_FAILED = "generate_failed"

    # 迁移步骤
    MIGRATE_STARTED = "migrate_started"
    MIGRATE_SUCCESS = "migrate_success"
    MIGRATE_FAILED = "migrate_failed"

    # 完成
    COMPLETED = "completed"

    # 重试
    RETRY = "retry"


class Submission(Model):
    """技能提交记录"""
    id = fields.IntField(pk=True)

    # 基本信息
    submission_id = fields.CharField(max_length=36, unique=True, index=True, description="UUID")

    # 工作流步骤
    current_step = fields.CharField(max_length=20, null=True, description="当前步骤")
    step_details = fields.JSONField(default=dict, description="步骤详情")

    name = fields.CharField(max_length=200, description="技能名称")
    repo_url = fields.CharField(max_length=500, null=True, description="仓库地址（ZIP上传时为空）")
    source_type = fields.CharField(max_length=10, default="git", description="来源类型: git 或 zip")
    zip_path = fields.CharField(max_length=500, null=True, description="ZIP文件路径（仅ZIP上传时使用）")
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

    # 处理结果
    skill_count = fields.IntField(default=0, description="发现的技能数")
    processed_skills = fields.IntField(default=0, description="处理成功的技能数")
    failed_skills = fields.IntField(default=0, description="处理失败的技能数")
    skill_slugs = fields.JSONField(null=True, description="技能slug列表")
    highest_risk = fields.CharField(max_length=20, null=True, description="最高风险等级")

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
    review_message = fields.TextField(null=True, description="审批意见（拒绝原因）")
    reviewed_at = fields.DatetimeField(null=True, description="审批时间")
    reviewer_id = fields.IntField(null=True, description="审批人ID")
    reviewer_employee_id = fields.CharField(max_length=20, null=True, description="审批人工号")

    # 时间戳
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
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
        return self.status == SubmissionStatus.FAILED

    @property
    def is_terminal(self) -> bool:
        """是否已到达终态"""
        return self.status in (
            SubmissionStatus.COMPLETED,
            SubmissionStatus.FAILED,
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
            "current_step": self.current_step,
            "step_details": self.step_details,
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
