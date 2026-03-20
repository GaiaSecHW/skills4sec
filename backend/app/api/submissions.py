"""
技能提交 API - 通过后端直接调用 Gitea API 创建 Issue
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, HttpUrl
from typing import Optional
import httpx

from app.config import settings

router = APIRouter(prefix="/submissions", tags=["submissions"])


class SkillSubmission(BaseModel):
    """技能提交数据模型"""
    name: str
    repo_url: str
    description: str
    category: Optional[str] = None
    contact: Optional[str] = None


class SubmissionResponse(BaseModel):
    """提交响应模型"""
    success: bool
    message: str
    issue_url: Optional[str] = None
    issue_number: Optional[int] = None


# Gitea 配置 - 从 settings 读取 (支持 .env 文件)
GITEA_API_URL = settings.GITEA_API_URL
GITEA_TOKEN = settings.GITEA_TOKEN
GITEA_REPO = settings.GITEA_REPO


@router.post("", response_model=SubmissionResponse)
async def submit_skill(submission: SkillSubmission):
    """
    提交技能 - 通过后端调用 Gitea API 创建 Issue

    无需用户登录 Gitea，后端使用配置的 token 代为创建 Issue。
    """
    if not GITEA_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务未配置 Gitea Token，请联系管理员"
        )

    # 构建 Issue 内容
    body_parts = [
        f"## 技能名称\n{submission.name}",
        f"## 仓库地址\n{submission.repo_url}",
    ]

    if submission.category:
        body_parts.append(f"## 分类\n{submission.category}")

    body_parts.append(f"## 描述\n{submission.description}")

    if submission.contact:
        body_parts.append(f"## 联系方式\n{submission.contact}")

    body = "\n\n".join(body_parts)

    # 调用 Gitea API 创建 Issue (禁用代理)
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
                issue_number = data.get("number")
                issue_url = data.get("html_url")

                # 添加 pending-approval 标签 (ID: 1)
                if issue_number:
                    try:
                        await client.post(
                            f"{GITEA_API_URL}/repos/{GITEA_REPO}/issues/{issue_number}/labels",
                            headers={
                                "Authorization": f"token {GITEA_TOKEN}",
                                "Content-Type": "application/json",
                            },
                            json={"labels": [1]}
                        )
                    except Exception:
                        pass  # 标签添加失败不影响主流程

                return SubmissionResponse(
                    success=True,
                    message="技能提交成功！请等待审核。",
                    issue_url=issue_url,
                    issue_number=issue_number
                )
            else:
                error_detail = response.text
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"创建 Issue 失败: {error_detail}"
                )

        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="请求超时，请稍后重试"
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"网络错误: {str(e)}"
            )


@router.get("/health")
async def submissions_health():
    """检查提交服务配置状态"""
    return {
        "configured": bool(GITEA_TOKEN),
        "gitea_url": GITEA_API_URL,
        "repo": GITEA_REPO
    }
