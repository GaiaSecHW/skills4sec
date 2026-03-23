"""
依赖注入 - FastAPI Depends 工具
"""
from typing import AsyncGenerator, Optional
from fastapi import Depends, Query
from tortoise.models import Model

from app.config import settings
from app.models.user import User
from app.utils.security import get_current_user
from app.core.exceptions import ForbiddenError


# ============ 分页依赖 ============

class PaginationParams:
    """分页参数"""
    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE, description="每页数量"),
    ):
        self.page = page
        self.page_size = page_size
        self.skip = (page - 1) * page_size
        self.limit = page_size


def get_pagination() -> PaginationParams:
    """获取分页参数依赖"""
    return Depends(PaginationParams)


# ============ 用户权限依赖 ============

async def get_current_user_dep(
    current_user: User = Depends(get_current_user)
) -> User:
    """获取当前用户（依赖注入版本）"""
    return current_user


async def get_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """获取管理员用户"""
    if current_user.role not in ("admin", "super_admin") and not current_user.is_superuser:
        raise ForbiddenError(message="需要管理员权限")
    return current_user


async def get_super_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """获取超级管理员"""
    if current_user.role != "super_admin" and not current_user.is_superuser:
        raise ForbiddenError(message="需要超级管理员权限")
    return current_user


# ============ 可选用户依赖 ============

async def get_optional_user(
    current_user: Optional[User] = Depends(get_current_user)
) -> Optional[User]:
    """获取可选用户（允许未登录）"""
    return current_user


# ============ Repository 依赖注入工厂 ============

def get_repository(repo_class):
    """
    Repository 依赖注入工厂

    Usage:
        @router.get("/users/{id}")
        async def get_user(
            id: int,
            repo: UserRepository = Depends(get_repository(UserRepository))
        ):
            return await repo.get_by_id(id)
    """
    def _get_repo():
        return repo_class()
    return Depends(_get_repo)
