"""
统计接口 - 无需鉴权
从 skills.json + download_stats.json 读取数据
"""
from fastapi import APIRouter, Query
from typing import Optional, List, Dict
from collections import Counter

from app.schemas.skill import (
    TopStatsOut, RankingItem, StatsPeriod, CategoryOut
)
from app.services.skill_loader import (
    load_skills_json, load_download_stats, increment_download,
)

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/top", response_model=TopStatsOut)
async def get_top_skills(
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
):
    """
    获取技能下载排行统计
    数据来源: skills.json + download_stats.json
    """
    all_skills = load_skills_json()
    download_stats = load_download_stats()

    # 合并下载计数，排除被阻止的技能
    skill_downloads = []
    for skill in all_skills:
        if skill.get("is_blocked", False):
            continue
        slug = skill.get("slug", "")
        skill_downloads.append({
            "name": skill.get("name", slug),
            "slug": slug,
            "downloads": download_stats.get(slug, 0),
            "author": skill.get("author", "未知"),
        })

    # 按下载量降序
    skill_downloads.sort(key=lambda x: x["downloads"], reverse=True)

    # TOP 20
    top_20 = skill_downloads[:20]
    total_downloads = sum(s["downloads"] for s in skill_downloads)

    rankings = []
    for idx, item in enumerate(top_20, 1):
        rankings.append(RankingItem(
            rank=idx,
            skill_name=item["name"],
            downloads=item["downloads"],
            author=item["author"],
        ))

    return TopStatsOut(
        period=StatsPeriod(start_date=start_date, end_date=end_date),
        total_downloads=total_downloads,
        rankings=rankings,
    )


@router.get("/summary")
async def get_stats_summary():
    """
    获取统计概览：技能总数、总下载量、风险分布、分类分布
    数据来源: skills.json + download_stats.json
    """
    all_skills = load_skills_json()
    download_stats = load_download_stats()

    # 过滤掉被阻止的
    active_skills = [s for s in all_skills if not s.get("is_blocked", False)]

    # 总下载量
    total_downloads = sum(download_stats.get(s.get("slug", ""), 0) for s in active_skills)

    # 风险分布
    risk_counts = {"safe": 0, "low": 0, "medium": 0, "high": 0, "critical": 0}
    for skill in active_skills:
        level = skill.get("risk_level", "safe")
        if level in risk_counts:
            risk_counts[level] += 1

    # 分类分布
    cat_counter: Counter = Counter()
    for skill in active_skills:
        cat = skill.get("category", "uncategorized")
        cat_counter[cat] += 1

    # 分类列表（按技能数量降序）
    categories = []
    for slug, count in cat_counter.most_common():
        cat_name = slug
        for skill in active_skills:
            if skill.get("category") == slug:
                cat_name = slug.replace("-", " ").replace("_", " ").title()
                break
        categories.append({
            "slug": slug,
            "name": cat_name,
            "icon": "📁",
            "skill_count": count,
        })

    return {
        "total_skills": len(active_skills),
        "total_downloads": total_downloads,
        "risk_distribution": risk_counts,
        "category_distribution": categories,
    }


@router.get("/favorites/top")
async def get_favorites_top(limit: int = Query(20, ge=1, le=100)):
    """
    获取收藏排行 TOP N
    数据来源: user_favorites 表 + skills.json
    """
    from app.models.favorite import UserFavorite
    from tortoise.functions import Count

    # 按技能分组统计收藏数
    top_favorites = await UserFavorite.annotate(
        fav_count=Count("id")
    ).group_by("skill_slug").order_by("-fav_count").limit(limit).values("skill_slug", "fav_count")

    if not top_favorites:
        return {"success": True, "total_favorites": 0, "rankings": []}

    # 统计总收藏数
    total_favorites = await UserFavorite.all().count()

    # 从 skills.json 补充技能名称和作者
    all_skills = load_skills_json()
    skill_map = {s.get("slug"): s for s in all_skills}

    rankings = []
    for idx, item in enumerate(top_favorites, 1):
        slug = item["skill_slug"]
        skill = skill_map.get(slug, {})
        rankings.append({
            "rank": idx,
            "slug": slug,
            "skill_name": skill.get("name", slug),
            "author": skill.get("author", "未知"),
            "favorites": item["fav_count"],
        })

    return {
        "success": True,
        "total_favorites": total_favorites,
        "rankings": rankings,
    }
