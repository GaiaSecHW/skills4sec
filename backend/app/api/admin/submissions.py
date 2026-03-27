"""
技能提交管理 API - 简化版工作流管理
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Request, UploadFile, Form
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field
from pathlib import Path
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
from tortoise.expressions import Q
from app.utils.security import get_current_admin_user, get_current_superuser
from app.services.workflow_service import workflow_service
from app.config import settings

router = APIRouter(prefix="/admin/submissions", tags=["admin-submissions"])


# ============ Schema 定义 ============

class SubmissionCreate(BaseModel):
    """创建提交请求"""
    name: Optional[str] = Field(None, max_length=200, description="技能名称（可选，从仓库解析或ZIP文件名获取）")
    repo_url: Optional[str] = Field(None, max_length=500, description="Git 仓库地址（ZIP上传时为空）")
    source_type: str = Field("git", max_length=10, description="来源类型: git 或 zip")
    description: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=50)
    contact: Optional[str] = Field(None, max_length=200)


class SubmissionOut(BaseModel):
    """提交输出"""
    id: int
    submission_id: str
    name: str
    repo_url: Optional[str]
    source_type: str
    zip_path: Optional[str]
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
        "source_type": sub.source_type,
        "zip_path": sub.zip_path,
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
        "review_message": sub.review_message,
        "reviewed_at": sub.reviewed_at,
        "reviewer_employee_id": sub.reviewer_employee_id,
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
        query = query.filter(Q(name__icontains=keyword) | Q(repo_url__icontains=keyword))

    if start_date:
        query = query.filter(created_at__gte=start_date)
    if end_date:
        query = query.filter(created_at__lte=end_date)

    total = await query.count()
    total = total if total is not None else 0
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
    # 验证 Git URL 格式（不允许 tree/blob/commit 等页面链接）
    if data.repo_url:
        if "/tree/" in data.repo_url or "/blob/" in data.repo_url or "/commit/" in data.repo_url:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="不支持的 URL 格式，请输入纯 Git 仓库地址（.git 结尾或 git@ 格式）")

    # 生成 UUID
    submission_id = str(uuid.uuid4())

    # 如果没有提供 name，尝试从 repo_url 解析或使用默认值
    name = data.name
    if not name:
        if data.repo_url:
            # 从 URL 提取 repo 名
            parts = data.repo_url.rstrip("/").rstrip(".git").split("/")
            name = parts[-1] if parts else "Unknown"
        else:
            name = "Unknown"

    submission = await Submission.create(
        submission_id=submission_id,
        name=name,
        repo_url=data.repo_url,
        source_type=data.source_type,
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


@router.post("/upload-zip", response_model=dict)
async def upload_zip(
    request: Request,
    file: UploadFile,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    contact: Optional[str] = Form(None),
    admin: User = Depends(get_current_admin_user)
):
    """上传 ZIP 压缩包创建提交（ZIP内直接包含 SKILL.md）"""
    # 验证文件类型
    if not file.filename or not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="只支持 ZIP 压缩包")

    # 生成 UUID 和路径
    submission_id = str(uuid.uuid4())
    zip_dir = Path(__file__).parent.parent.parent / "skills_zip_temp"
    zip_dir.mkdir(exist_ok=True)
    zip_path = zip_dir / f"{submission_id}.zip"

    # 保存上传的文件
    try:
        content = await file.read()
        with open(zip_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    # 验证 ZIP 内容（检查是否包含 SKILL.md）
    import zipfile
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            namelist = zf.namelist()
            has_skill_md = any("SKILL.md" in name for name in namelist)
            if not has_skill_md:
                # 删除临时文件
                zip_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="ZIP 内未找到 SKILL.md 文件")
    except zipfile.BadZipFile:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="无效的 ZIP 文件")

    # 自动从 SKILL.md 提取名称
    skill_name = name
    if not skill_name:
        skill_name = "Unknown"
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # 查找 SKILL.md 文件
                skill_md_path = None
                for n in namelist:
                    if n.endswith("SKILL.md"):
                        skill_md_path = n
                        break

                if skill_md_path:
                    content = zf.read(skill_md_path).decode('utf-8')
                    # 从 markdown 标题提取名称 (# skill-name)
                    for line in content.split('\n')[:10]:
                        if line.startswith('# '):
                            skill_name = line[2:].strip()
                            break
        except Exception:
            pass

    # 创建提交记录
    submission = await Submission.create(
        submission_id=submission_id,
        name=skill_name,
        repo_url=None,
        source_type="zip",
        zip_path=str(zip_path),
        description=description,
        category=category,
        contact=contact,
        submitter_id=admin.id,
        submitter_employee_id=admin.employee_id,
        status=SubmissionStatus.PENDING,
    )

    # 记录创建事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.CREATED,
        message=f"管理员 {admin.employee_id} 通过 ZIP 上传创建提交",
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    return {
        "success": True,
        "message": "ZIP 上传成功",
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


@router.post("/{submission_id}/continue", response_model=dict)
async def continue_workflow(
    request: Request,
    submission_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """继续执行工作流（用于卡在中间状态或失败后重试）"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    # COMPLETED 是终态不允许继续，FAILED 允许重试
    if submission.status == SubmissionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"终态 {submission.status} 不允许继续"
        )

    # pending 状态走 start
    if submission.status == SubmissionStatus.PENDING:
        asyncio.create_task(workflow_service.start_workflow(submission))
        return {
            "success": True,
            "message": "工作流已启动",
            "data": submission_to_out(submission)
        }

    # 根据当前状态确定下一步
    next_step = None
    current_status = submission.status

    # 状态 -> 下一步的映射
    status_to_step = {
        SubmissionStatus.CREATING_ISSUE: "cloning",  # Issue 创建中 -> 继续克隆
        SubmissionStatus.ISSUE_CREATED: "cloning",   # Issue 已创建 -> 开始克隆
        SubmissionStatus.ISSUE_FAILED: "cloning",     # Issue 失败 -> 重试克隆
        SubmissionStatus.CLONING: "cloning",          # 克隆中 -> 重新克隆
        SubmissionStatus.GENERATING: "generating",    # 生成中 -> 重新生成
        SubmissionStatus.MIGRATING: "migrating",      # 迁移中 -> 重新迁移
        SubmissionStatus.APPROVED: "cloning",         # 已批准 -> 开始克隆
        SubmissionStatus.PROCESSING: "cloning",       # 处理中 -> 开始克隆
        SubmissionStatus.PR_CREATED: "cloning",        # PR 已创建 -> 开始克隆
        SubmissionStatus.FAILED: "cloning",            # 失败 -> 从克隆重试
    }

    next_step = status_to_step.get(current_status)

    if not next_step:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法确定下一步，当前状态: {current_status}"
        )

    # 记录继续事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.RETRY,
        message=f"管理员 {admin.employee_id} 继续工作流 (从 {current_status.value})",
        details={"from_status": current_status.value, "step": next_step},
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    # 如果克隆已完成，自动执行完整流程（无论是失败恢复还是克隆后的继续）
    cloning_info = submission.step_details.get("cloning", {})
    if cloning_info.get("status") == "completed":
        # 使用 continue_workflow 自动完成剩余步骤
        asyncio.create_task(workflow_service.continue_workflow(submission))
        return {
            "success": True,
            "message": "工作流继续执行（生成+迁移）",
            "data": submission_to_out(submission)
        }

    # 否则执行指定步骤
    asyncio.create_task(workflow_service.execute_step(submission, next_step))

    return {
        "success": True,
        "message": f"工作流继续执行 {next_step}",
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

    # 只允许删除已完成、失败或被拒绝的提交
    if submission.status not in (SubmissionStatus.COMPLETED, SubmissionStatus.FAILED, SubmissionStatus.REJECTED):
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


class ReviewRequest(BaseModel):
    """审批请求"""
    message: Optional[str] = Field(None, max_length=1000, description="审批意见/拒绝原因")


@router.post("/{submission_id}/approve", response_model=dict)
async def approve_submission(
    submission_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """审批通过"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    # 更新状态
    submission.status = SubmissionStatus.APPROVED
    submission.review_message = None
    submission.reviewed_at = datetime.utcnow()
    submission.reviewer_id = admin.id
    submission.reviewer_employee_id = admin.employee_id
    await submission.save()

    # 记录事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.RETRY,  # 复用，表示状态变更
        old_status=submission.status,
        new_status=SubmissionStatus.APPROVED,
        message=f"管理员 {admin.employee_id} 审批通过",
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    return {
        "success": True,
        "message": "审批通过",
        "data": submission_to_out(submission)
    }


@router.post("/{submission_id}/reject", response_model=dict)
async def reject_submission(
    submission_id: int,
    data: ReviewRequest,
    admin: User = Depends(get_current_admin_user)
):
    """审批拒绝"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    old_status = submission.status

    # 更新状态
    submission.status = SubmissionStatus.REJECTED
    submission.review_message = data.message or "审核不通过"
    submission.reviewed_at = datetime.utcnow()
    submission.reviewer_id = admin.id
    submission.reviewer_employee_id = admin.employee_id
    await submission.save()

    # 记录事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.RETRY,
        old_status=old_status,
        new_status=SubmissionStatus.REJECTED,
        message=f"管理员 {admin.employee_id} 审批拒绝: {data.message or '无原因'}",
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    return {
        "success": True,
        "message": "已拒绝",
        "data": submission_to_out(submission)
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
