"""
用户收藏接口 - 需要登录
"""
from fastapi import APIRouter, Depends, Query
from typing import List, Optional

from app.models.user import User
from app.models.favorite import UserFavorite
from app.utils.security import get_current_user
from app.core.exceptions import NotFoundError, ConflictError
from app.core.logging import get_logger
from app.services.skill_loader import load_skills_json, find_skill_by_slug

logger = get_logger("favorites")

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.post("/{slug}")
async def add_favorite(
    slug: str,
    current_user: User = Depends(get_current_user),
):
    """收藏技能"""
    skill = find_skill_by_slug(slug)
    if not skill:
        raise NotFoundError(message="技能不存在", detail={"slug": slug})

    exists = await UserFavorite.exists(user_id=current_user.id, skill_slug=slug)
    if exists:
        raise ConflictError(message="已收藏该技能", detail={"slug": slug})

    await UserFavorite.create(user_id=current_user.id, skill_slug=slug)
    logger.info(f'{{"event": "favorite_added", "user_id": {current_user.id}, "slug": "{slug}"}}')

    return {"success": True, "message": "收藏成功"}


@router.delete("/{slug}")
async def remove_favorite(
    slug: str,
    current_user: User = Depends(get_current_user),
):
    """取消收藏"""
    fav = await UserFavorite.get_or_none(user_id=current_user.id, skill_slug=slug)
    if not fav:
        raise NotFoundError(message="未收藏该技能", detail={"slug": slug})

    await fav.delete()
    logger.info(f'{{"event": "favorite_removed", "user_id": {current_user.id}, "slug": "{slug}"}}')

    return {"success": True, "message": "已取消收藏"}


@router.get("/my")
async def get_my_favorites(
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的收藏列表"""
    favorites = await UserFavorite.filter(
        user_id=current_user.id
    ).order_by("-created_at").limit(200)

    if not favorites:
        return {"success": True, "data": []}

    # 批量查 skills.json 获取技能详情
    all_skills = load_skills_json()
    skill_map = {s.get("slug"): s for s in all_skills}

    result = []
    for fav in favorites:
        skill = skill_map.get(fav.skill_slug)
        if skill and not skill.get("is_blocked", False):
            result.append({
                "slug": fav.skill_slug,
                "name": skill.get("name", fav.skill_slug),
                "icon": skill.get("icon", "📦"),
                "description": skill.get("description", ""),
                "summary": skill.get("summary", ""),
                "category": skill.get("category", ""),
                "author": skill.get("author", ""),
                "risk_level": skill.get("risk_level", "safe"),
                "supported_tools": skill.get("supported_tools", []),
                "favorited_at": fav.created_at.isoformat() if fav.created_at else None,
            })

    return {"success": True, "data": result}


@router.get("/check")
async def check_favorites(
    slugs: str = Query(..., description="逗号分隔的技能 slug 列表"),
    current_user: User = Depends(get_current_user),
):
    """批量检查技能是否已收藏"""
    slug_list = [s.strip() for s in slugs.split(",") if s.strip()][:50]
    if not slug_list:
        return {"success": True, "data": {}}

    favorites = await UserFavorite.filter(
        user_id=current_user.id,
        skill_slug__in=slug_list,
    ).values_list("skill_slug", flat=True)

    result = {slug: (slug in favorites) for slug in slug_list}
    return {"success": True, "data": result}


@router.get("/count/{slug}")
async def get_favorite_count(slug: str):
    """获取技能被收藏次数（无需登录）"""
    count = await UserFavorite.filter(skill_slug=slug).count()
    return {"success": True, "slug": slug, "count": count}
