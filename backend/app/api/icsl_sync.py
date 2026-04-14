"""
ICSL 组织同步 API 路由
"""
from typing import Optional

from fastapi import APIRouter, Header, Request

from app.services.icsl_sync_service import icsl_sync_service
from app.core import get_logger

logger = get_logger("icsl_sync_api")

router = APIRouter(prefix="/icsl", tags=["icsl-sync"])


@router.post("/sync/full")
async def trigger_full_sync():
    """手动触发全量同步 (从 icsl 组织拉取所有 skill)"""
    result = await icsl_sync_service.full_sync()
    return {"status": "ok", "result": result}


@router.post("/sync/{repo_name}")
async def trigger_single_sync(repo_name: str):
    """手动触发单个仓库同步"""
    success, msg = await icsl_sync_service.sync_single_repo(repo_name)
    return {"success": success, "message": msg}


@router.post("/push/{slug}")
async def push_skill_to_icsl(slug: str):
    """推送本地 skill 到 icsl 组织"""
    # 先检查重名
    exists, info = await icsl_sync_service.check_name_conflict(slug)
    if exists:
        return {
            "success": False,
            "message": f"repo {slug} already exists in icsl",
            "existing_repo": info,
        }
    success, msg = await icsl_sync_service.push_skill(slug)
    return {"success": success, "message": msg}


@router.get("/status")
async def get_sync_status():
    """获取同步状态"""
    return icsl_sync_service.get_sync_status()


@router.get("/check/{slug}")
async def check_conflict(slug: str):
    """检查 skill 是否在 icsl 已存在同名仓库"""
    exists, info = await icsl_sync_service.check_name_conflict(slug)
    return {"exists": exists, "info": info}


@router.post("/webhook")
async def handle_webhook(
    request: Request,
    x_gitea_event: Optional[str] = Header(None),
    x_gitea_delivery: Optional[str] = Header(None),
):
    """
    处理 Gitea Organization Webhook

    Gitea 会在以下事件触发:
    - create: 新 tag 创建
    - push: 代码推送到 main
    """
    payload = await request.json()
    event_type = x_gitea_event or payload.get("action", "unknown")

    logger.info(f'{{"event": "webhook_received", "type": "{event_type}"}}')

    result = await icsl_sync_service.handle_webhook(payload)
    return {"status": "processed", "result": result}


@router.post("/rebuild")
async def rebuild_site():
    """手动触发前端数据重建 (重新生成 skills.json)"""
    success, msg = await icsl_sync_service.rebuild_site()
    return {"success": success, "message": msg}


@router.post("/register-webhook")
async def register_webhook():
    """为 icsl 组织注册 Webhook (需配置外部访问地址)"""
    from app.config import settings

    # 推导 webhook 目标地址
    # 从 Gitea API URL 中提取域名, 拼接 backend 路径
    # 生产环境应使用外部域名
    api_url = settings.ICSL_GITEA_API_URL
    # 简单推导: http://skillhub-gitea.ns.svc:3000/api/v1 -> 不适合外部访问
    # 应该用 skillhub.ai.icsl.huawei.com 域名
    # 这里提供一个参数让用户指定, 或者从环境变量读取
    external_url = getattr(settings, "ICSL_WEBHOOK_EXTERNAL_URL", "")
    if not external_url:
        return {
            "success": False,
            "message": "ICSL_WEBHOOK_EXTERNAL_URL not configured, "
                       "set it to your backend external URL (e.g. https://skillhub.ai.icsl.huawei.com)",
        }

    target_url = f"{external_url.rstrip('/')}/api/icsl/webhook"
    success, msg = await icsl_sync_service.register_org_webhook(target_url)
    return {"success": success, "message": msg}
