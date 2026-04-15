"""
技能提交 API - 使用 Repository 模式 + 事务管理
"""
from fastapi import APIRouter, Request, Depends, UploadFile, Form, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid
import httpx
import asyncio

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
from app.services.workflow_service import workflow_service

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

    async with httpx.AsyncClient(timeout=30.0, trust_env=False, follow_redirects=True, verify=False) as client:
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
    background_tasks: BackgroundTasks,
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

        # 自动启动工作流（带错误处理）
        # 保存 submission_id 而不是对象，避免数据库连接问题
        submission_id = submission.submission_id

        async def run_workflow_with_error_handling():
            try:
                # 重新获取 submission 对象，使用新的数据库连接
                from tortoise import Tortoise
                from app.config import settings

                # 确保数据库连接已初始化
                if not Tortoise._inited:
                    await Tortoise.init(
                        db_url=settings.DATABASE_URL,
                        modules={'models': ['app.models.user', 'app.models.submission', 'app.models.skill']}
                    )

                sub = await Submission.get_or_none(submission_id=submission_id)
                if sub:
                    success, message = await workflow_service.start_workflow(sub)
                    logger.info("工作流完成", event="workflow_completed", business={"submission_id": submission_id, "success": success})
                else:
                    logger.error("找不到提交记录", event="workflow_error", business={"submission_id": submission_id})
            except Exception as e:
                logger.error("工作流执行失败", event="workflow_error", business={"submission_id": submission_id}, error=str(e))
                import traceback
                logger.error(traceback.format_exc())

        background_tasks.add_task(run_workflow_with_error_handling)

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


@router.post("/upload-zip", response_model=dict)
async def upload_zip_public(
    request: Request,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    contact: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    """公开的 ZIP 上传接口（需要登录）"""
    from pathlib import Path
    import zipfile

    # 验证文件类型
    if not file.filename or not file.filename.lower().endswith('.zip'):
        raise ValidationError(message="只支持 ZIP 压缩包")

    # 生成 UUID 和路径
    submission_id = str(uuid.uuid4())
    zip_dir = Path(__file__).parent.parent / "skills_zip_temp"
    zip_dir.mkdir(exist_ok=True)
    zip_path = zip_dir / f"{submission_id}.zip"

    # 保存上传的文件
    try:
        content = await file.read()
        with open(zip_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise ValidationError(message=f"文件保存失败: {str(e)}")

    # 验证 ZIP 内容
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            namelist = zf.namelist()
            has_skill_md = any("SKILL.md" in name for name in namelist)
            if not has_skill_md:
                zip_path.unlink(missing_ok=True)
                raise ValidationError(message="ZIP 内未找到 SKILL.md 文件")
    except zipfile.BadZipFile:
        zip_path.unlink(missing_ok=True)
        raise ValidationError(message="无效的 ZIP 文件")

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

    # 获取客户端信息
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

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
        submitter_id=current_user.id,
        submitter_employee_id=current_user.employee_id,
        submitter_ip=client_ip,
        submitter_user_agent=user_agent,
        status=SubmissionStatus.PENDING,
    )

    # 记录创建事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.CREATED,
        new_status=SubmissionStatus.PENDING,
        message=f"用户 {current_user.employee_id} 通过 ZIP 上传创建提交",
        triggered_by="user"
    )

    # 自动启动工作流（带错误处理）
    # 保存 submission_id 而不是对象，避免数据库连接问题
    submission_id = submission.submission_id

    async def run_workflow_with_error_handling():
        try:
            # 重新获取 submission 对象，使用新的数据库连接
            from tortoise import Tortoise
            from app.config import settings

            # 确保数据库连接已初始化
            if not Tortoise._inited:
                await Tortoise.init(
                    db_url=settings.DATABASE_URL,
                    modules={'models': ['app.models.user', 'app.models.submission', 'app.models.skill']}
                )

            sub = await Submission.get_or_none(submission_id=submission_id)
            if sub:
                success, message = await workflow_service.start_workflow(sub)
                logger.info("工作流完成", event="workflow_completed", business={"submission_id": submission_id, "success": success})
            else:
                logger.error("找不到提交记录", event="workflow_error", business={"submission_id": submission_id})
        except Exception as e:
            logger.error("工作流执行失败", event="workflow_error", business={"submission_id": submission_id}, error=str(e))
            import traceback
            logger.error(traceback.format_exc())

    background_tasks.add_task(run_workflow_with_error_handling)

    return {
        "success": True,
        "message": "ZIP 上传成功，工作流已启动",
        "data": {
            "submission_id": submission.submission_id,
            "name": submission.name,
            "status": submission.status.value if isinstance(submission.status, SubmissionStatus) else submission.status,
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
                "current_step": s.current_step,
                "highest_risk": s.highest_risk,
                "retry_count": s.retry_count,
                "max_retries": s.max_retries,
                "error_message": s.error_message,
                "review_message": s.review_message,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in submissions
        ]
    }
