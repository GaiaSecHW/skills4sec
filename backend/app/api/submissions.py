"""
技能提交 API - 使用 Repository 模式 + 事务管理
"""
from fastapi import APIRouter, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid
import httpx

from app.models.submission import (
    Submission,
    SubmissionEvent,
    SubmissionStatus,
    SubmissionEventType
)
from app.models.user import User
from app.config import settings
from app.core import (
    NotFoundError,
    ValidationError,
    atomic,
    get_repository,
)
from app.core.harness_logging import HarnessLogger
from app.repositories import SubmissionRepository
from app.utils.security import get_current_user
from app.utils import build_issue_body

logger = HarnessLogger("submissions")
router = APIRouter(prefix="/submissions", tags=["submissions"])
security = HTTPBearer(auto_error=False)


class SkillSubmission(BaseModel):
    """技能提交数据模型"""
    name: str = Field(..., min_length=1, max_length=200)
    repo_url: str = Field(..., max_length=500)
    description: str = Field("", max_length=2000)
    category: Optional[str] = Field(None, max_length=50)
    contact: Optional[str] = Field(None, max_length=200)


class SubmissionResponse(BaseModel):
    """提交响应模型"""
    success: bool
    message: str
    submission_id: Optional[str] = None
    issue_url: Optional[str] = None
    issue_number: Optional[int] = None


# Gitea 配置
GITEA_API_URL = settings.GITEA_API_URL
GITEA_TOKEN = settings.GITEA_TOKEN
GITEA_REPO = settings.GITEA_REPO


async def create_gitea_issue(submission: Submission) -> tuple[bool, str, Optional[dict]]:
    """
    调用 Gitea API 创建 Issue

    Returns:
        (是否成功, 消息, Issue数据)
    """
    if not GITEA_TOKEN:
        return False, "服务未配置 Gitea Token", None

    body = build_issue_body(submission)

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        try:
            response = await client.post(
                f"{GITEA_API_URL}/repos/{GITEA_REPO}/issues",
                headers={
                    "Authorization": f"token {GITEA_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "title": f"[技能提交] {submission.name}",
                    "body": body,
                }
            )

            if response.status_code == 201:
                data = response.json()

                # 添加 pending-approval 标签 (ID: 1)
                if data.get("number"):
                    try:
                        await client.post(
                            f"{GITEA_API_URL}/repos/{GITEA_REPO}/issues/{data['number']}/labels",
                            headers={
                                "Authorization": f"token {GITEA_TOKEN}",
                                "Content-Type": "application/json",
                            },
                            json={"labels": [1]}
                        )
                    except Exception:
                        pass  # 标签添加失败不影响主流程

                return True, "Issue 创建成功", data

            else:
                error_detail = response.text[:500]
                return False, f"创建 Issue 失败: {error_detail}", None

        except Exception as e:
            logger.error("Gitea Issue 创建错误", event="gitea_issue_error", error=str(e))
            return False, f"网络错误: {str(e)}", None


@router.post("", response_model=SubmissionResponse)
@atomic
async def submit_skill(
    submission_data: SkillSubmission,
    request: Request,
    current_user: User = Depends(get_current_user),
    repo: SubmissionRepository = get_repository(SubmissionRepository),
):
    """
    提交技能 - 通过后端调用 Gitea API 创建 Issue

    需要用户登录，后端使用配置的 token 代为创建 Issue。
    """
    if not GITEA_TOKEN:
        raise ValidationError(
            message="服务未配置 Gitea Token，请联系管理员",
            detail={"service": "gitea"}
        )

    # 获取客户端信息
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    # 从 JWT token 获取提交者信息
    submitter_id = current_user.id
    submitter_employee_id = current_user.employee_id

    # 创建提交记录
    submission = await repo.create(
        submission_id=str(uuid.uuid4()),
        name=submission_data.name,
        repo_url=submission_data.repo_url,
        description=submission_data.description,
        category=submission_data.category,
        contact=submission_data.contact,
        submitter_id=submitter_id,
        submitter_employee_id=submitter_employee_id,
        submitter_ip=client_ip,
        submitter_user_agent=user_agent,
        status=SubmissionStatus.CREATING_ISSUE,
    )

    # 记录创建事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.CREATED,
        new_status=SubmissionStatus.CREATING_ISSUE,
        message="提交已创建，正在创建 Issue",
        details={
            "name": submission_data.name,
            "repo_url": submission_data.repo_url,
        },
        triggered_by="user"
    )

    logger.info("技能提交已创建", event="submission_created", business={"submission_id": submission.submission_id, "name": submission.name})

    # 尝试创建 Issue
    success, message, issue_data = await create_gitea_issue(submission)

    if success:
        # 更新提交状态
        submission.status = SubmissionStatus.ISSUE_CREATED
        submission.issue_number = issue_data.get("number")
        submission.issue_url = issue_data.get("html_url")
        submission.issue_created_at = datetime.utcnow()
        await submission.save()

        # 记录成功事件
        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.ISSUE_CREATE_SUCCESS,
            old_status=SubmissionStatus.CREATING_ISSUE,
            new_status=SubmissionStatus.ISSUE_CREATED,
            message=f"Issue #{submission.issue_number} 创建成功",
            details={
                "issue_number": submission.issue_number,
                "issue_url": submission.issue_url,
            },
            triggered_by="system"
        )

        logger.info("Issue 创建成功", event="issue_created", business={"submission_id": submission.submission_id, "issue_number": submission.issue_number})

        return SubmissionResponse(
            success=True,
            message="技能提交成功！请等待审核。",
            submission_id=submission.submission_id,
            issue_url=submission.issue_url,
            issue_number=submission.issue_number
        )
    else:
        # 创建失败，安排重试
        submission.status = SubmissionStatus.ISSUE_FAILED
        submission.error_message = message
        await submission.save()

        # 记录失败事件
        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.ISSUE_CREATE_FAILED,
            old_status=SubmissionStatus.CREATING_ISSUE,
            new_status=SubmissionStatus.ISSUE_FAILED,
            message=f"Issue 创建失败: {message}",
            error_message=message,
            triggered_by="system"
        )

        # 安排自动重试
        from app.services.retry_service import retry_service
        await retry_service.schedule_retry(submission, message)

        logger.warning("Issue 创建失败", event="issue_failed", business={"submission_id": submission.submission_id, "error": message})

        return SubmissionResponse(
            success=True,
            message="技能已提交，但 Issue 创建暂时失败。系统会自动重试，请稍后查看状态。",
            submission_id=submission.submission_id,
        )


@router.get("/health")
async def submissions_health():
    """检查提交服务配置状态"""
    return {
        "configured": bool(GITEA_TOKEN),
        "gitea_url": GITEA_API_URL,
        "repo": GITEA_REPO
    }


@router.get("/{submission_id}/status")
async def get_submission_status(
    submission_id: str,
    repo: SubmissionRepository = get_repository(SubmissionRepository),
):
    """获取提交状态 (通过 submission_id)"""
    submission = await repo.find_by_submission_id(submission_id)
    if not submission:
        raise NotFoundError(
            message="提交不存在",
            detail={"submission_id": submission_id}
        )

    return {
        "success": True,
        "data": {
            "submission_id": submission.submission_id,
            "name": submission.name,
            "status": submission.status.value if isinstance(submission.status, SubmissionStatus) else submission.status,
            "issue_number": submission.issue_number,
            "issue_url": submission.issue_url,
            "pr_number": submission.pr_number,
            "pr_url": submission.pr_url,
            "error_message": submission.error_message,
            "created_at": submission.created_at.isoformat() if submission.created_at else None,
            "updated_at": submission.updated_at.isoformat() if submission.updated_at else None,
        }
    }


@router.get("/my")
async def get_my_submissions(
    current_user: User = Depends(get_current_user),
    repo: SubmissionRepository = get_repository(SubmissionRepository),
):
    """获取当前用户的提交记录"""
    submissions = await Submission.filter(
        submitter_id=current_user.id
    ).order_by("-created_at").limit(100)

    return {
        "success": True,
        "data": [
            {
                "id": s.id,
                "submission_id": s.submission_id,
                "name": s.name,
                "repo_url": s.repo_url,
                "description": s.description,
                "category": s.category,
                "status": s.status.value if isinstance(s.status, SubmissionStatus) else s.status,
                "issue_number": s.issue_number,
                "issue_url": s.issue_url,
                "pr_number": s.pr_number,
                "pr_url": s.pr_url,
                "highest_risk": s.highest_risk,
                "retry_count": s.retry_count,
                "max_retries": s.max_retries,
                "error_message": s.error_message,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in submissions
        ]
    }
