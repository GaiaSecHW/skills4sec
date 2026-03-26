"""
技能提交管理 API - 工作流监控和重试管理
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum
import uuid
import csv
import io

from app.models.user import User
from app.models.submission import (
    Submission,
    SubmissionEvent,
    SubmissionStatus,
    SubmissionEventType
)
from app.utils.security import get_current_admin_user, get_current_superuser
from app.services.retry_service import retry_service
from app.services.gitea_sync_service import gitea_sync_service
from app.config import settings
from app.core.exceptions import NotFoundError, ValidationError, ForbiddenError

router = APIRouter(prefix="/admin/submissions", tags=["admin-submissions"])


# ============ 辅助函数 ============

def _enum_value(enum_obj, default=None):
    """安全地提取枚举值，兼容枚举类型和字符串"""
    if enum_obj is None:
        return default
    if isinstance(enum_obj, Enum):
        return enum_obj.value
    return enum_obj


def _get_status_value(submission: Submission) -> str:
    """获取提交状态值（兼容枚举和字符串）"""
    return _enum_value(submission.status)


router = APIRouter(prefix="/admin/submissions", tags=["admin-submissions"])


# ============ Schema 定义 ============

class SubmissionCreate(BaseModel):
    """创建提交请求"""
    name: str = Field(..., min_length=1, max_length=200)
    repo_url: str = Field(..., max_length=500)
    description: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=50)
    contact: Optional[str] = Field(None, max_length=200)


class SubmissionOut(BaseModel):
    """提交输出"""
    id: int
    submission_id: str
    name: str
    repo_url: str
    description: Optional[str]
    category: Optional[str]
    contact: Optional[str]
    submitter_employee_id: Optional[str]
    status: str
    issue_number: Optional[int]
    issue_url: Optional[str]
    pr_number: Optional[int]
    pr_url: Optional[str]
    skill_count: int
    processed_skills: int
    failed_skills: int
    highest_risk: Optional[str]
    retry_count: int
    max_retries: int
    next_retry_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    issue_created_at: Optional[datetime]
    processing_started_at: Optional[datetime]
    processing_completed_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class SubmissionEventOut(BaseModel):
    """提交事件输出"""
    id: int
    submission_id: int
    event_type: str
    old_status: Optional[str]
    new_status: Optional[str]
    message: Optional[str]
    details: Optional[dict]
    triggered_by: Optional[str]
    actor_employee_id: Optional[str]
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SubmissionDetail(BaseModel):
    """提交详情（含事件）"""
    submission: SubmissionOut
    events: List[SubmissionEventOut]


class SubmissionStats(BaseModel):
    """提交统计"""
    total: int
    pending: int
    processing: int
    completed: int
    failed: int
    by_status: dict
    by_risk: dict
    today_count: int
    avg_processing_time_seconds: Optional[float]


class RetryRequest(BaseModel):
    """重试请求"""
    reset_count: bool = Field(
        False,
        description="是否重置重试计数（用于已达到最大重试次数的情况）"
    )


class RejectRequest(BaseModel):
    """拒绝请求"""
    reason: str = Field(..., min_length=1, max_length=500)


class BatchRetryRequest(BaseModel):
    """批量重试请求"""
    submission_ids: List[int] = Field(..., min_items=1, max_items=50)


# ============ 辅助函数 ============

def submission_to_out(sub: Submission) -> dict:
    """转换为输出格式"""
    return {
        "id": sub.id,
        "submission_id": sub.submission_id,
        "name": sub.name,
        "repo_url": sub.repo_url,
        "description": sub.description,
        "category": sub.category,
        "contact": sub.contact,
        "submitter_employee_id": sub.submitter_employee_id,
        "status": sub.status.value if isinstance(sub.status, SubmissionStatus) else sub.status,
        "issue_number": sub.issue_number,
        "issue_url": sub.issue_url,
        "pr_number": sub.pr_number,
        "pr_url": sub.pr_url,
        "skill_count": sub.skill_count,
        "processed_skills": sub.processed_skills,
        "failed_skills": sub.failed_skills,
        "highest_risk": sub.highest_risk,
        "retry_count": sub.retry_count,
        "max_retries": sub.max_retries,
        "next_retry_at": sub.next_retry_at,
        "error_message": sub.error_message,
        "created_at": sub.created_at,
        "updated_at": sub.updated_at,
        "issue_created_at": sub.issue_created_at,
        "processing_started_at": sub.processing_started_at,
        "processing_completed_at": sub.processing_completed_at,
        "completed_at": sub.completed_at,
    }


def event_to_out(event: SubmissionEvent) -> dict:
    """转换事件为输出格式"""
    return {
        "id": event.id,
        "submission_id": event.submission_id,
        "event_type": event.event_type.value if isinstance(event.event_type, SubmissionEventType) else event.event_type,
        "old_status": event.old_status.value if event.old_status and isinstance(event.old_status, SubmissionStatus) else event.old_status,
        "new_status": event.new_status.value if event.new_status and isinstance(event.new_status, SubmissionStatus) else event.new_status,
        "message": event.message,
        "details": event.details,
        "triggered_by": event.triggered_by,
        "actor_employee_id": event.actor_employee_id,
        "error_message": event.error_message,
        "created_at": event.created_at,
    }


# ============ API 接口 ============

@router.get("", response_model=dict)
async def list_submissions(
    request: Request,
    skip: int = Query(0, ge=0, description="偏移量"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选"),
    risk: Optional[str] = Query(None, description="风险等级筛选"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    start_date: Optional[datetime] = Query(None, description="开始时间"),
    end_date: Optional[datetime] = Query(None, description="结束时间"),
    admin: User = Depends(get_current_admin_user)
):
    """获取提交列表 (管理员) - 支持分页、筛选和关键词搜索"""
    query = Submission.all()

    if status:
        try:
            status_enum = SubmissionStatus(status)
            query = query.filter(status=status_enum)
        except ValueError:
            pass

    if risk:
        query = query.filter(highest_risk=risk)

    if keyword:
        query = query.filter(name__icontains=keyword) | Submission.filter(repo_url__icontains=keyword)

    if start_date:
        query = query.filter(created_at__gte=start_date)
    if end_date:
        query = query.filter(created_at__lte=end_date)

    total = await query.count()
    submissions = await query.offset(skip).limit(limit).order_by("-created_at")

    return {
        "success": True,
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [submission_to_out(s) for s in submissions]
    }


@router.get("/stats", response_model=dict)
async def get_submission_stats(
    admin: User = Depends(get_current_admin_user)
):
    """获取提交统计 (管理员)"""
    from datetime import date

    # 总数和按状态统计
    total = await Submission.all().count()

    by_status = {}
    for s in SubmissionStatus:
        count = await Submission.filter(status=s).count()
        by_status[s.value] = count

    # 按风险等级统计
    by_risk = {}
    for risk in ["safe", "low", "medium", "high", "critical"]:
        count = await Submission.filter(highest_risk=risk).count()
        by_risk[risk] = count

    # 今日新增
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_count = await Submission.filter(created_at__gte=today_start).count()

    # 计算平均处理时间
    completed = await Submission.filter(
        processing_started_at__isnull=False,
        processing_completed_at__isnull=False
    ).all()

    avg_time = None
    if completed:
        total_seconds = sum(
            (s.processing_completed_at - s.processing_started_at).total_seconds()
            for s in completed
        )
        avg_time = total_seconds / len(completed)

    return {
        "success": True,
        "data": {
            "total": total,
            "pending": by_status.get("pending", 0) + by_status.get("creating_issue", 0) + by_status.get("issue_created", 0),
            "processing": by_status.get("processing", 0) + by_status.get("approved", 0),
            "completed": by_status.get("merged", 0) + by_status.get("closed", 0),
            "failed": by_status.get("issue_failed", 0) + by_status.get("process_failed", 0),
            "by_status": by_status,
            "by_risk": by_risk,
            "today_count": today_count,
            "avg_processing_time_seconds": avg_time
        }
    }


@router.get("/failed", response_model=dict)
async def list_failed_submissions(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_current_admin_user)
):
    """获取失败的提交列表 (需要关注的)"""
    failed_statuses = [
        SubmissionStatus.ISSUE_FAILED,
        SubmissionStatus.PROCESS_FAILED
    ]

    query = Submission.filter(status__in=failed_statuses)
    total = await query.count()
    submissions = await query.offset(skip).limit(limit).order_by("-updated_at")

    return {
        "success": True,
        "total": total,
        "data": [submission_to_out(s) for s in submissions]
    }


# ============ 趋势统计 API (必须在 /{submission_id} 之前) ============

@router.get("/trends", response_model=dict)
async def get_submission_trends(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
    admin: User = Depends(get_current_admin_user)
):
    """获取提交趋势数据"""
    from datetime import date, timedelta

    trends = []
    today = date.today()

    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        day_start = datetime.combine(d, datetime.min.time())
        day_end = datetime.combine(d, datetime.max.time())

        count = await Submission.filter(
            created_at__gte=day_start,
            created_at__lte=day_end
        ).count()

        completed = await Submission.filter(
            created_at__gte=day_start,
            created_at__lte=day_end,
            status__in=[SubmissionStatus.MERGED, SubmissionStatus.CLOSED]
        ).count()

        failed = await Submission.filter(
            created_at__gte=day_start,
            created_at__lte=day_end,
            status__in=[SubmissionStatus.ISSUE_FAILED, SubmissionStatus.PROCESS_FAILED]
        ).count()

        trends.append({
            "date": d.isoformat(),
            "total": count,
            "completed": completed,
            "failed": failed
        })

    return {
        "success": True,
        "data": {
            "trends": trends,
            "days": days
        }
    }


@router.get("/{submission_id}", response_model=dict)
async def get_submission_detail(
    submission_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """获取提交详情 (含事件日志)"""
    submission = await Submission.get_or_none(id=submission_id).prefetch_related("events")
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    events = await submission.events.all().order_by("created_at")

    return {
        "success": True,
        "data": {
            "submission": submission_to_out(submission),
            "events": [event_to_out(e) for e in events]
        }
    }


@router.get("/{submission_id}/workflow-progress", response_model=dict)
async def get_submission_workflow_progress(
    submission_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """获取提交的工作流运行进度"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    # 获取工作流运行进度
    progress = await gitea_sync_service.get_workflow_run_progress(submission)

    return {
        "success": True,
        "data": progress
    }


@router.post("/{submission_id}/retry", response_model=dict)
async def retry_submission(
    request: Request,
    submission_id: int,
    retry_data: Optional[RetryRequest] = None,
    admin: User = Depends(get_current_admin_user)
):
    """手动重试失败的提交"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    if not submission.is_retryable:
        # 检查是否需要重置计数
        if retry_data and retry_data.reset_count:
            submission.retry_count = 0
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"当前状态 {submission.status} 不支持重试，或已达到最大重试次数"
            )

    success, message = await retry_service.execute_retry(submission)

    # 记录管理员操作
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.MANUAL_OVERRIDE,
        message=f"管理员 {admin.employee_id} 触发手动重试",
        details={"admin_id": admin.id, "result": message},
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    return {
        "success": success,
        "message": message,
        "data": submission_to_out(submission)
    }


@router.post("/{submission_id}/approve", response_model=dict)
async def approve_submission(
    request: Request,
    submission_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """审批通过提交"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    if submission.status != SubmissionStatus.ISSUE_CREATED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态 {submission.status} 不支持审批操作"
        )

    old_status = submission.status
    submission.status = SubmissionStatus.APPROVED
    submission.approved_by = admin.id
    submission.approved_by_employee_id = admin.employee_id
    submission.approved_at = datetime.utcnow()
    await submission.save()

    # 记录事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.APPROVED,
        old_status=old_status,
        new_status=SubmissionStatus.APPROVED,
        message=f"管理员 {admin.employee_id} 审批通过",
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    # 添加 Issue 评论
    if submission.issue_number:
        await gitea_sync_service.add_issue_comment(
            submission.issue_number,
            f"✅ **已审批通过** by @{admin.employee_id}\n\n已进入安全审计队列，等待自动处理..."
        )

    # 设置为待审计状态，由 APScheduler 的 run_security_audit 任务自动处理
    submission.status = SubmissionStatus.PENDING_AUDIT
    await submission.save()

    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.PROCESSING_STARTED,
        old_status=SubmissionStatus.APPROVED,
        new_status=SubmissionStatus.PENDING_AUDIT,
        message="已进入安全审计队列",
        triggered_by="system"
    )

    return {
        "success": True,
        "message": "审批成功，已进入安全审计队列",
        "data": submission_to_out(submission)
    }


@router.post("/{submission_id}/reject", response_model=dict)
async def reject_submission(
    request: Request,
    submission_id: int,
    reject_data: RejectRequest,
    admin: User = Depends(get_current_admin_user)
):
    """拒绝提交"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    if submission.status not in (SubmissionStatus.ISSUE_CREATED, SubmissionStatus.APPROVED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态 {submission.status} 不支持拒绝操作"
        )

    old_status = submission.status
    submission.status = SubmissionStatus.REJECTED
    submission.rejected_by = admin.id
    submission.rejected_by_employee_id = admin.employee_id
    submission.rejected_at = datetime.utcnow()
    submission.reject_reason = reject_data.reason
    submission.completed_at = datetime.utcnow()
    await submission.save()

    # 记录事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.REJECTED,
        old_status=old_status,
        new_status=SubmissionStatus.REJECTED,
        message=f"管理员 {admin.employee_id} 拒绝: {reject_data.reason}",
        details={"reason": reject_data.reason},
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    # 关闭 Issue
    if submission.issue_number:
        await gitea_sync_service.close_issue(
            submission.issue_number,
            f"管理员 {admin.employee_id} 拒绝: {reject_data.reason}"
        )

    return {
        "success": True,
        "message": "已拒绝",
        "data": submission_to_out(submission)
    }


@router.post("/{submission_id}/force-process", response_model=dict)
async def force_process_submission(
    request: Request,
    submission_id: int,
    admin: User = Depends(get_current_superuser)
):
    """强制触发处理 (仅超级管理员，跳过审批)"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    if submission.is_terminal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该提交已到达终态，无法处理"
        )

    # 记录事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.MANUAL_OVERRIDE,
        message=f"超级管理员 {admin.employee_id} 强制触发处理",
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="super_admin"
    )

    # 设置为待审计状态，由 APScheduler 自动处理
    old_status = submission.status
    submission.status = SubmissionStatus.PENDING_AUDIT
    await submission.save()

    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.PROCESSING_STARTED,
        old_status=old_status,
        new_status=SubmissionStatus.PENDING_AUDIT,
        message="已强制进入安全审计队列",
        triggered_by="super_admin"
    )

    return {
        "success": True,
        "message": "已强制进入安全审计队列",
        "data": submission_to_out(submission)
    }


@router.post("/batch-retry", response_model=dict)
async def batch_retry_submissions(
    request: Request,
    batch_data: BatchRetryRequest,
    admin: User = Depends(get_current_admin_user)
):
    """批量重试失败的提交"""
    results = {
        "success_count": 0,
        "failed_count": 0,
        "details": []
    }

    for sub_id in batch_data.submission_ids:
        submission = await Submission.get_or_none(id=sub_id)
        if not submission:
            results["failed_count"] += 1
            results["details"].append({
                "id": sub_id,
                "success": False,
                "message": "提交不存在"
            })
            continue

        if not submission.is_retryable:
            results["failed_count"] += 1
            results["details"].append({
                "id": sub_id,
                "success": False,
                "message": f"状态 {submission.status} 不支持重试"
            })
            continue

        success, message = await retry_service.execute_retry(submission)

        if success:
            results["success_count"] += 1
        else:
            results["failed_count"] += 1

        results["details"].append({
            "id": sub_id,
            "success": success,
            "message": message
        })

    return {
        "success": True,
        "message": f"成功重试 {results['success_count']} 个，失败 {results['failed_count']} 个",
        "data": results
    }


@router.get("/export/csv")
async def export_submissions_csv(
    request: Request,
    status: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    admin: User = Depends(get_current_admin_user)
):
    """导出提交记录为 CSV"""
    query = Submission.all()

    if status:
        try:
            status_enum = SubmissionStatus(status)
            query = query.filter(status=status_enum)
        except ValueError:
            pass

    if start_date:
        query = query.filter(created_at__gte=start_date)
    if end_date:
        query = query.filter(created_at__lte=end_date)

    submissions = await query.order_by("-created_at")

    output = io.StringIO()
    output.write('\ufeff')  # UTF-8 BOM
    writer = csv.writer(output)

    writer.writerow([
        "提交ID", "技能名称", "仓库地址", "状态", "提交者",
        "Issue编号", "PR编号", "风险等级", "重试次数",
        "错误信息", "创建时间", "更新时间"
    ])

    for sub in submissions:
        writer.writerow([
            sub.submission_id,
            sub.name,
            sub.repo_url,
            sub.status.value if isinstance(sub.status, SubmissionStatus) else sub.status,
            sub.submitter_employee_id or "",
            sub.issue_number or "",
            sub.pr_number or "",
            sub.highest_risk or "",
            f"{sub.retry_count}/{sub.max_retries}",
            (sub.error_message or "")[:200],
            sub.created_at.isoformat() if sub.created_at else "",
            sub.updated_at.isoformat() if sub.updated_at else "",
        ])

    output.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=submissions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )


# ============ 调度器状态 API ============

@router.get("/scheduler/status", response_model=dict)
async def get_scheduler_status(
    admin: User = Depends(get_current_admin_user)
):
    """获取调度器状态"""
    from app.tasks.scheduler import get_scheduler_status
    status = get_scheduler_status()
    return {
        "success": True,
        "data": status
    }


@router.post("/scheduler/run-task", response_model=dict)
async def run_scheduler_task(
    request: Request,
    task_data: dict,
    admin: User = Depends(get_current_superuser)
):
    """手动触发定时任务 (仅超级管理员)"""
    from app.tasks.scheduler import run_task_manually

    task_name = task_data.get("task_name")
    if not task_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 task_name 参数"
        )

    result = await run_task_manually(task_name)

    # 记录操作日志
    if result.get("success"):
        await SubmissionEvent.create(
            submission_id=0,  # 系统事件
            event_type=SubmissionEventType.MANUAL_OVERRIDE,
            message=f"超级管理员 {admin.employee_id} 手动触发任务: {task_name}",
            details={"task_name": task_name, "result": result},
            actor_id=admin.id,
            actor_employee_id=admin.employee_id,
            triggered_by="super_admin"
        )

    return {
        "success": result.get("success", False),
        "message": "任务执行完成" if result.get("success") else result.get("error", "执行失败"),
        "data": result
    }


# ============ 工作流调试 API (白盒化调试) ============

class WorkflowStepDetail(BaseModel):
    """工作流步骤详情"""
    step_id: str
    step_name: str
    status: str  # pending, running, success, failed, skipped
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None
    can_trigger: bool = False
    can_reset: bool = False


class SubmissionWorkflowDebug(BaseModel):
    """提交工作流调试信息"""
    submission_id: int
    current_status: str
    current_step: str
    steps: List[WorkflowStepDetail] = []
    available_actions: List[str] = []
    last_error: Optional[str] = None
    retry_info: dict = {}


# 工作流步骤定义
WORKFLOW_STEPS = [
    {
        "id": "create_issue",
        "name": "创建 Issue",
        "description": "在 Gitea 创建 Issue 用于跟踪提交",
        "trigger_statuses": ["pending", "issue_failed"],
        "success_status": "issue_created",
        "failure_status": "issue_failed",
    },
    {
        "id": "approve",
        "name": "审批",
        "description": "管理员审批通过提交",
        "trigger_statuses": ["issue_created"],
        "success_status": "approved",
        "failure_status": "rejected",
    },
    {
        "id": "security_audit",
        "name": "安全审计",
        "description": "AI 自动进行安全审计",
        "trigger_statuses": ["approved", "pending_audit"],
        "success_status": "processing",
        "failure_status": "audit_failed",
    },
    {
        "id": "sync_gitea",
        "name": "同步 Gitea",
        "description": "从 Gitea 同步 Issue/PR/Workflow 状态",
        "trigger_statuses": ["processing", "issue_created", "approved"],
        "success_status": None,  # 不改变状态，只是同步
        "failure_status": None,
    },
    {
        "id": "trigger_workflow",
        "name": "触发工作流",
        "description": "触发 Gitea Actions 工作流",
        "trigger_statuses": ["approved", "pending_audit"],
        "success_status": "processing",
        "failure_status": "process_failed",
    },
]


@router.get("/{submission_id}/debug-info", response_model=dict)
async def get_submission_debug_info(
    submission_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """
    获取提交的工作流调试信息

    返回每个步骤的详细状态、可执行操作、执行历史等
    """
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    # 获取事件历史
    events = await SubmissionEvent.filter(submission=submission).order_by("created_at")
    events_list = [event_to_out(e) for e in events]

    # 构建步骤详情
    steps_detail = []
    for step in WORKFLOW_STEPS:
        step_detail = await _build_step_detail(submission, step, events)
        steps_detail.append(step_detail)

    # 确定当前步骤
    current_step = _get_current_step(submission.status.value if isinstance(submission.status, SubmissionStatus) else submission.status)

    # 可用操作
    available_actions = _get_available_actions(submission, admin)

    return {
        "success": True,
        "data": {
            "submission_id": submission.id,
            "submission_uuid": submission.submission_id,
            "current_status": submission.status.value if isinstance(submission.status, SubmissionStatus) else submission.status,
            "current_step": current_step,
            "steps": steps_detail,
            "available_actions": available_actions,
            "last_error": submission.error_message,
            "retry_info": {
                "retry_count": submission.retry_count,
                "max_retries": submission.max_retries,
                "next_retry_at": submission.next_retry_at.isoformat() if submission.next_retry_at else None,
                "is_retryable": submission.is_retryable,
            },
            "events": events_list,
            "raw_data": {
                "issue_number": submission.issue_number,
                "issue_url": submission.issue_url,
                "pr_number": submission.pr_number,
                "pr_url": submission.pr_url,
                "workflow_run_id": submission.workflow_run_id,
                "workflow_run_url": submission.workflow_run_url,
                "highest_risk": submission.highest_risk,
                "skill_count": submission.skill_count,
                "processed_skills": submission.processed_skills,
                "failed_skills": submission.failed_skills,
            }
        }
    }


async def _build_step_detail(submission: Submission, step: dict, events: list) -> dict:
    """构建步骤详情"""
    step_id = step["id"]

    # 根据步骤类型确定状态
    status_map = {
        "create_issue": _get_issue_step_status(submission, events),
        "approve": _get_approve_step_status(submission, events),
        "security_audit": _get_audit_step_status(submission, events),
        "sync_gitea": _get_sync_step_status(submission, events),
        "trigger_workflow": _get_workflow_step_status(submission, events),
    }

    step_status = status_map.get(step_id, {"status": "pending", "message": None, "error": None})

    # 判断是否可以触发
    current_status = submission.status.value if isinstance(submission.status, SubmissionStatus) else submission.status
    can_trigger = current_status in step.get("trigger_statuses", [])

    # 判断是否可以重置
    can_reset = step_status["status"] == "failed"

    return {
        "step_id": step_id,
        "step_name": step["name"],
        "description": step["description"],
        "status": step_status["status"],
        "started_at": step_status.get("started_at"),
        "completed_at": step_status.get("completed_at"),
        "duration_seconds": step_status.get("duration_seconds"),
        "message": step_status.get("message"),
        "error": step_status.get("error") or submission.error_message if step_status["status"] == "failed" else None,
        "can_trigger": can_trigger,
        "can_reset": can_reset,
    }


def _get_issue_step_status(submission: Submission, events: list) -> dict:
    """获取创建 Issue 步骤状态"""
    current_status = submission.status.value if isinstance(submission.status, SubmissionStatus) else submission.status

    if submission.issue_number:
        # Issue 已创建
        created_event = next((e for e in events if e.event_type == SubmissionEventType.ISSUE_CREATE_SUCCESS), None)
        return {
            "status": "success",
            "started_at": submission.created_at,
            "completed_at": submission.issue_created_at or created_event.created_at if created_event else None,
            "message": f"Issue #{submission.issue_number} 已创建",
        }
    elif current_status == "creating_issue":
        return {
            "status": "running",
            "started_at": submission.created_at,
            "message": "正在创建 Issue...",
        }
    elif current_status == "issue_failed":
        failed_event = next((e for e in reversed(events) if e.event_type == SubmissionEventType.ISSUE_CREATE_FAILED), None)
        return {
            "status": "failed",
            "started_at": submission.created_at,
            "error": failed_event.error_message if failed_event else submission.error_message,
            "message": "Issue 创建失败",
        }
    else:
        return {
            "status": "pending",
            "message": "等待创建 Issue",
        }


def _get_approve_step_status(submission: Submission, events: list) -> dict:
    """获取审批步骤状态"""
    current_status = submission.status.value if isinstance(submission.status, SubmissionStatus) else submission.status

    if current_status in ["approved", "pending_audit", "processing", "merged", "closed", "pr_created"]:
        approved_event = next((e for e in events if e.event_type == SubmissionEventType.APPROVED), None)
        return {
            "status": "success",
            "started_at": submission.issue_created_at,
            "completed_at": approved_event.created_at if approved_event else submission.approved_at,
            "message": f"由 {submission.approved_by_employee_id or '管理员'} 审批通过",
        }
    elif current_status == "rejected":
        return {
            "status": "failed",
            "error": submission.reject_reason,
            "message": f"被拒绝: {submission.reject_reason}",
        }
    elif current_status == "issue_created":
        return {
            "status": "pending",
            "started_at": submission.issue_created_at,
            "message": "等待管理员审批",
        }
    else:
        return {
            "status": "pending",
            "message": "等待进入审批环节",
        }


def _get_audit_step_status(submission: Submission, events: list) -> dict:
    """获取安全审计步骤状态"""
    current_status = submission.status.value if isinstance(submission.status, SubmissionStatus) else submission.status

    if current_status in ["processing", "pr_created", "merged"]:
        return {
            "status": "success",
            "started_at": submission.processing_started_at,
            "completed_at": submission.processing_completed_at,
            "message": f"安全审计完成，风险等级: {submission.highest_risk or '未知'}",
            "duration_seconds": submission.duration_seconds,
        }
    elif current_status == "pending_audit":
            return {
            "status": "pending",
            "started_at": submission.approved_at,
            "message": "等待安全审计",
        }
    elif current_status in ["process_failed", "audit_failed"]:
            return {
            "status": "failed",
                "started_at": submission.processing_started_at,
                "completed_at": submission.processing_completed_at,
                "error": submission.error_message,
                "message": "安全审计失败",
            }
    else:
        return {
            "status": "pending",
            "message": "等待进入审计环节",
        }


def _get_sync_step_status(submission: Submission, events: list) -> dict:
    """获取同步状态步骤"""
    sync_events = [e for e in events if e.event_type == SubmissionEventType.STATUS_SYNCED]

    if sync_events:
        last_sync = sync_events[-1]
        return {
            "status": "success",
            "completed_at": last_sync.created_at,
            "message": f"最后同步: {last_sync.created_at.strftime('%H:%M:%S')}",
        }
    elif submission.issue_number or submission.pr_number:
        return {
            "status": "success",
            "message": "已有 Gitea 关联数据",
        }
    else:
        return {
            "status": "pending",
            "message": "等待同步",
        }


def _get_workflow_step_status(submission: Submission, events: list) -> dict:
    """获取工作流步骤状态"""
    current_status = submission.status.value if isinstance(submission.status, SubmissionStatus) else submission.status

    if current_status == "processing":
        return {
            "status": "running",
            "started_at": submission.processing_started_at,
            "message": "Gitea Actions 工作流执行中...",
        }
    elif current_status in ["pr_created", "merged"]:
        return {
            "status": "success",
            "started_at": submission.processing_started_at,
            "completed_at": submission.processing_completed_at,
            "message": f"工作流执行成功，PR #{submission.pr_number} 已创建" if submission.pr_number else "工作流执行成功",
            "duration_seconds": submission.duration_seconds,
        }
    elif current_status == "process_failed":
        return {
            "status": "failed",
            "started_at": submission.processing_started_at,
            "completed_at": submission.processing_completed_at,
            "error": submission.error_message,
            "message": "工作流执行失败",
        }
    else:
        return {
            "status": "pending",
            "message": "等待触发工作流",
        }


def _get_current_step(status: str) -> str:
    """根据状态获取当前步骤"""
    step_map = {
        "pending": "create_issue",
        "creating_issue": "create_issue",
        "issue_created": "approve",
        "issue_failed": "create_issue",
        "approved": "security_audit",
        "rejected": "approve",
        "pending_audit": "security_audit",
        "audit_failed": "security_audit",
        "processing": "trigger_workflow",
        "process_failed": "trigger_workflow",
        "needs_review": "security_audit",
        "pr_created": "trigger_workflow",
        "merged": "trigger_workflow",
        "closed": "trigger_workflow",
    }
    return step_map.get(status, "unknown")


def _get_available_actions(submission: Submission, admin: User) -> List[str]:
    """获取可用的操作"""
    actions = []
    current_status = _get_status_value(submission)
    is_super_admin = admin.role == "super_admin"

    # 基础操作映射（所有管理员可执行）
    status_actions = {
        "pending": ["create_issue"],
        "issue_failed": ["retry_create_issue"],
        "issue_created": ["approve", "reject"],
        "approved": ["trigger_audit"],
        "pending_audit": ["trigger_audit"],
        "processing": ["sync_status"],
        "process_failed": ["retry_process"],
        "audit_failed": ["retry_audit"],
    }

    actions.extend(status_actions.get(current_status, []))

    # 超级管理员专属操作
    if is_super_admin:
        if current_status == "issue_failed":
            actions.append("force_create_issue")
        if current_status in ["approved", "pending_audit"]:
            actions.append("force_process")
        if current_status == "processing":
            actions.append("force_complete")
        if current_status in ["process_failed", "audit_failed"]:
            actions.append("force_reset")

    return actions


# ============ 工作流手动触发接口 ============

@router.post("/{submission_id}/trigger/create-issue", response_model=dict)
async def manual_create_issue(
    submission_id: int,
    request: Request,
    admin: User = Depends(get_current_admin_user)
):
    """
    手动创建 Issue

    用于调试或重试 Issue 创建
    """
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    current_status = submission.status.value if isinstance(submission.status, SubmissionStatus) else submission.status
    if current_status not in ["pending", "issue_failed", "creating_issue"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态 {current_status} 不支持此操作"
        )

    # 记录操作
    old_status = submission.status
    submission.status = SubmissionStatus.CREATING_ISSUE
    await submission.save()

    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.MANUAL_OVERRIDE,
        old_status=old_status,
        new_status=SubmissionStatus.CREATING_ISSUE,
        message=f"管理员 {admin.employee_id} 手动触发创建 Issue",
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    # 执行创建
    from app.api.submissions import create_gitea_issue
    success, message, issue_data = await create_gitea_issue(submission)

    if success:
        submission.status = SubmissionStatus.ISSUE_CREATED
        submission.issue_number = issue_data.get("number")
        submission.issue_url = issue_data.get("html_url")
        submission.issue_created_at = datetime.utcnow()
        await submission.save()

        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.ISSUE_CREATE_SUCCESS,
            old_status=SubmissionStatus.CREATING_ISSUE,
            new_status=SubmissionStatus.ISSUE_CREATED,
            message=f"Issue #{submission.issue_number} 创建成功",
            details={"issue_number": submission.issue_number, "issue_url": submission.issue_url},
            triggered_by="admin"
        )

        return {
            "success": True,
            "message": f"Issue #{submission.issue_number} 创建成功",
            "data": {
                "issue_number": submission.issue_number,
                "issue_url": submission.issue_url,
            }
        }
    else:
        submission.status = SubmissionStatus.ISSUE_FAILED
        submission.error_message = message
        await submission.save()

        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.ISSUE_CREATE_FAILED,
            old_status=SubmissionStatus.CREATING_ISSUE,
            new_status=SubmissionStatus.ISSUE_FAILED,
            message=f"Issue 创建失败: {message}",
            error_message=message,
            triggered_by="admin"
        )

        return {
            "success": False,
            "message": f"Issue 创建失败: {message}",
            "data": {"error": message}
        }


@router.post("/{submission_id}/trigger/audit", response_model=dict)
async def manual_trigger_audit(
    submission_id: int,
    request: Request,
    admin: User = Depends(get_current_admin_user)
):
    """
    手动触发安全审计

    跳过审批直接进入审计队列
    """
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    current_status = submission.status.value if isinstance(submission.status, SubmissionStatus) else submission.status
    if current_status not in ["approved", "pending_audit", "issue_created"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态 {current_status} 不支持此操作"
        )

    # 记录操作
    old_status = submission.status
    submission.status = SubmissionStatus.PENDING_AUDIT
    submission.approved_by = admin.id
    submission.approved_by_employee_id = admin.employee_id
    submission.approved_at = datetime.utcnow()
    await submission.save()

    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.MANUAL_OVERRIDE,
        old_status=old_status,
        new_status=SubmissionStatus.PENDING_AUDIT,
        message=f"管理员 {admin.employee_id} 手动触发安全审计",
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    return {
        "success": True,
        "message": "已触发安全审计，等待后台任务处理",
        "data": submission_to_out(submission)
    }


@router.post("/{submission_id}/trigger/sync", response_model=dict)
async def manual_sync_status(
    submission_id: int,
    request: Request,
    admin: User = Depends(get_current_admin_user)
):
    """
    手动同步 Gitea 状态

    从 Gitea 拉取最新的 Issue/PR/Workflow 状态
    """
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    if not submission.issue_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该提交没有关联的 Issue"
        )

    # 记录操作
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.MANUAL_OVERRIDE,
        message=f"管理员 {admin.employee_id} 手动同步状态",
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    # 执行同步
    changed = await gitea_sync_service.sync_submission(submission)

    return {
        "success": True,
        "message": f"状态同步完成，{'有变化' if changed else '无变化'}",
        "data": {
            "changed": changed,
            "submission": submission_to_out(submission)
        }
    }


@router.post("/{submission_id}/trigger/workflow", response_model=dict)
async def manual_trigger_workflow(
    submission_id: int,
    request: Request,
    admin: User = Depends(get_current_superuser)
):
    """
    手动触发 Gitea Actions 工作流 (仅超级管理员)
    """
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    current_status = submission.status.value if isinstance(submission.status, SubmissionStatus) else submission.status
    if current_status not in ["approved", "pending_audit", "processing"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态 {current_status} 不支持此操作"
        )

    # 记录操作
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.MANUAL_OVERRIDE,
        message=f"超级管理员 {admin.employee_id} 手动触发工作流",
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="super_admin"
    )

    # 触发工作流
    success, message, run_id = await gitea_sync_service.trigger_workflow(submission)

    if success:
        if run_id:
            submission.workflow_run_id = run_id
        await submission.save()

        return {
            "success": True,
            "message": message,
            "data": {
                "run_id": run_id,
                "submission": submission_to_out(submission)
            }
        }
    else:
        return {
            "success": False,
            "message": message,
            "data": {"error": message}
        }


@router.post("/{submission_id}/reset-status", response_model=dict)
async def reset_submission_status(
    submission_id: int,
    request: Request,
    status_data: dict,
    admin: User = Depends(get_current_superuser)
):
    """
    重置提交状态 (仅超级管理员，用于调试)

    可以将提交重置到任意状态，用于调试或修复卡住的问题
    """
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    new_status = status_data.get("status")
    if not new_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 status 参数"
        )

    try:
        new_status_enum = SubmissionStatus(new_status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的状态: {new_status}"
        )

    # 记录操作
    old_status = submission.status
    submission.status = new_status_enum
    submission.error_message = None
    submission.retry_count = 0
    await submission.save()

    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.MANUAL_OVERRIDE,
        old_status=old_status,
        new_status=new_status_enum,
        message=f"超级管理员 {admin.employee_id} 重置状态为 {new_status}",
        details={"old_status": str(old_status), "new_status": new_status},
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="super_admin"
    )

    return {
        "success": True,
        "message": f"状态已重置为 {new_status}",
        "data": submission_to_out(submission)
    }


@router.get("/{submission_id}/execution-log", response_model=dict)
async def get_execution_log(
    submission_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """
    获取执行日志

    返回详细的事件日志，包含错误堆栈和执行详情
    """
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    events = await SubmissionEvent.filter(submission=submission).order_by("created_at")

    # 构建详细日志
    log_entries = []
    for event in events:
        entry = {
            "id": event.id,
            "time": event.created_at.isoformat(),
            "event_type": event.event_type.value if isinstance(event.event_type, SubmissionEventType) else event.event_type,
            "old_status": event.old_status.value if event.old_status and isinstance(event.old_status, SubmissionStatus) else event.old_status,
            "new_status": event.new_status.value if event.new_status and isinstance(event.new_status, SubmissionStatus) else event.new_status,
            "message": event.message,
            "details": event.details,
            "triggered_by": event.triggered_by,
            "actor": event.actor_employee_id,
            "error": event.error_message,
        }
        log_entries.append(entry)

    return {
        "success": True,
        "data": {
                "submission_id": submission.submission_id,
                "total_events": len(log_entries),
                "events": log_entries,
            }
        }
