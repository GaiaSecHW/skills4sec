"""
技能提交管理 API - 简化版工作流管理
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field
import uuid
import csv
import io
import asyncio

from app.models.user import User
from app.models.submission import (
    Submission,
    SubmissionEvent,
    SubmissionStatus,
    SubmissionEventType
)
from app.utils.security import get_current_admin_user, get_current_superuser
from app.services.workflow_service import workflow_service
from app.config import settings

router = APIRouter(prefix="/admin/submissions", tags=["admin-submissions"])


# ============ Schema 定义 ============

class SubmissionCreate(BaseModel):
    """创建提交请求"""
    name: Optional[str] = Field(None, max_length=200, description="技能名称（可选，从仓库解析）")
    repo_url: str = Field(..., max_length=500, description="Git 仓库地址")
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
    current_step: Optional[str]
    step_details: dict
    skill_count: int
    processed_skills: int
    failed_skills: int
    highest_risk: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
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


class StartWorkflowRequest(BaseModel):
    """启动工作流请求"""
    pass


class RetryStepRequest(BaseModel):
    """重试步骤请求"""
    step: str = Field(..., description="步骤名称: cloning/generating/migrating")


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
        "current_step": sub.current_step,
        "step_details": sub.step_details or {},
        "skill_count": sub.skill_count,
        "processed_skills": sub.processed_skills,
        "failed_skills": sub.failed_skills,
        "highest_risk": sub.highest_risk,
        "error_message": sub.error_message,
        "created_at": sub.created_at,
        "updated_at": sub.updated_at,
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
        "error_message": event.error_message,
        "created_at": event.created_at,
    }


# ============ API 接口 ============

@router.get("", response_model=dict)
async def list_submissions(
    request: Request,
    skip: int = Query(0, ge=0, description="偏移量"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    status_filter: Optional[str] = Query(None, alias="status", description="状态筛选"),
    risk: Optional[str] = Query(None, description="风险等级筛选"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    start_date: Optional[datetime] = Query(None, description="开始时间"),
    end_date: Optional[datetime] = Query(None, description="结束时间"),
    admin: User = Depends(get_current_admin_user)
):
    """获取提交列表 (管理员) - 支持分页、筛选和关键词搜索"""
    query = Submission.all()

    if status_filter:
        try:
            status_enum = SubmissionStatus(status_filter)
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
    # 总数和按状态统计
    total = await Submission.all().count()

    by_status = {}
    for s in SubmissionStatus:
        count = await Submission.filter(status=s).count()
        by_status[s.value] = count

    # 按风险等级统计
    by_risk = {}
    for risk_level in ["safe", "low", "medium", "high", "critical"]:
        count = await Submission.filter(highest_risk=risk_level).count()
        by_risk[risk_level] = count

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
            "pending": by_status.get("pending", 0),
            "processing": by_status.get("cloning", 0) + by_status.get("generating", 0) + by_status.get("migrating", 0),
            "completed": by_status.get("completed", 0),
            "failed": by_status.get("failed", 0),
            "by_status": by_status,
            "by_risk": by_risk,
            "today_count": today_count,
            "avg_processing_time_seconds": avg_time
        }
    }


@router.post("", response_model=dict)
async def create_submission(
    request: Request,
    data: SubmissionCreate,
    admin: User = Depends(get_current_admin_user)
):
    """创建提交"""
    # 生成 UUID
    submission_id = str(uuid.uuid4())

    # 如果没有提供 name，尝试从 repo_url 解析
    name = data.name
    if not name:
        # 从 URL 提取 repo 名
        parts = data.repo_url.rstrip("/").rstrip(".git").split("/")
        name = parts[-1] if parts else "Unknown"

    submission = await Submission.create(
        submission_id=submission_id,
        name=name,
        repo_url=data.repo_url,
        description=data.description,
        category=data.category,
        contact=data.contact,
        submitter_id=admin.id,
        submitter_employee_id=admin.employee_id,
        status=SubmissionStatus.PENDING,
    )

    # 记录创建事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.CREATED,
        message=f"管理员 {admin.employee_id} 创建提交",
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    return {
        "success": True,
        "message": "提交创建成功",
        "data": submission_to_out(submission)
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


@router.post("/{submission_id}/start", response_model=dict)
async def start_workflow(
    request: Request,
    submission_id: int,
    req_data: StartWorkflowRequest = None,
    admin: User = Depends(get_current_admin_user)
):
    """开始处理提交"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    if submission.status != SubmissionStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态 {submission.status} 不支持启动"
        )

    # 在后台启动工作流
    asyncio.create_task(workflow_service.start_workflow(submission))

    return {
        "success": True,
        "message": "工作流已启动",
        "data": submission_to_out(submission)
    }


@router.post("/{submission_id}/retry-step", response_model=dict)
async def retry_step(
    request: Request,
    submission_id: int,
    data: RetryStepRequest,
    admin: User = Depends(get_current_admin_user)
):
    """重试单个步骤"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    if submission.status != SubmissionStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有失败状态才能重试"
        )

    valid_steps = ["cloning", "generating", "migrating"]
    if data.step not in valid_steps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效步骤，可选: {valid_steps}"
        )

    # 记录重试事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.RETRY,
        message=f"管理员 {admin.employee_id} 重试步骤: {data.step}",
        details={"step": data.step},
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    # 在后台执行步骤
    asyncio.create_task(workflow_service.execute_step(submission, data.step))

    return {
        "success": True,
        "message": f"步骤 {data.step} 重试中",
        "data": submission_to_out(submission)
    }


@router.delete("/{submission_id}", response_model=dict)
async def delete_submission(
    submission_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """删除提交"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    # 只允许删除已完成或失败的提交
    if submission.status not in (SubmissionStatus.COMPLETED, SubmissionStatus.FAILED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态 {submission.status} 不支持删除"
        )

    submission_id_str = submission.submission_id
    await submission.delete()

    return {
        "success": True,
        "message": "提交已删除",
        "data": {"submission_id": submission_id_str}
    }


@router.get("/export/csv")
async def export_submissions_csv(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    admin: User = Depends(get_current_admin_user)
):
    """导出提交记录为 CSV"""
    query = Submission.all()

    if status_filter:
        try:
            status_enum = SubmissionStatus(status_filter)
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
        "提交ID", "技能名称", "仓库地址", "状态", "当前步骤",
        "提交者", "风险等级", "错误信息", "创建时间", "更新时间"
    ])

    for sub in submissions:
        writer.writerow([
            sub.submission_id,
            sub.name,
            sub.repo_url,
            sub.status.value if isinstance(sub.status, SubmissionStatus) else sub.status,
            sub.current_step or "",
            sub.submitter_employee_id or "",
            sub.highest_risk or "",
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
