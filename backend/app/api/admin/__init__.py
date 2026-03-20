"""
Admin API 模块 - 用户管理和提交管理
"""
from fastapi import APIRouter

from app.api.admin.users import router as users_router
from app.api.admin.submissions import router as submissions_router

# 创建统一的 admin 路由
router = APIRouter()

# 包含用户管理路由 (前缀 /admin)
router.include_router(users_router)

# 包含提交管理路由 (前缀 /admin/submissions)
router.include_router(submissions_router)
