"""
技能提交管理 API - 工作流监控和重试管理
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
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
            f"✅ **已审批通过** by @{admin.employee_id}\n\n正在触发处理工作流..."
        )

    # 触发处理工作流
    success, message, _ = await gitea_sync_service.trigger_workflow(submission)

    return {
        "success": True,
        "message": "审批成功" + ("，工作流已触发" if success else f"，但工作流触发失败: {message}"),
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

    success, message, run_id = await gitea_sync_service.trigger_workflow(submission)

    return {
        "success": success,
        "message": message,
        "data": {
            **submission_to_out(submission),
            "workflow_run_id": run_id
        }
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
