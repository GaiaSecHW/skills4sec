"""
统计接口 - 无需鉴权
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime

from app.models.skill import Skill
from app.schemas.skill import TopStatsOut, RankingItem, StatsPeriod

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/top", response_model=TopStatsOut)
async def get_top_skills(
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
):
    """
    获取技能下载排行统计

    权限: 无需认证
    """
    # 查询非阻止的技能，按下载次数降序
    query = Skill.filter(is_blocked=False)

    # 如果有日期筛选，仍返回全量排行（download_count无日期字段，仅作展示用）
    # 日期筛选仅影响period返回值
    skills = await query.order_by("-download_count").limit(100)

    total_downloads = sum(s.download_count or 0 for s in skills)

    rankings = []
    for idx, skill in enumerate(skills, 1):
        rankings.append(RankingItem(
            rank=idx,
            skill_name=skill.name,
            downloads=skill.download_count or 0,
            author=skill.author or "未知"
        ))

    return TopStatsOut(
        period=StatsPeriod(
            start_date=start_date,
            end_date=end_date
        ),
        total_downloads=total_downloads,
        rankings=rankings
    )
