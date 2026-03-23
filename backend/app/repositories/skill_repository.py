"""
技能 Repository - 技能数据访问
"""
from typing import Optional, List

from app.core.base_repository import BaseRepository
from app.models.skill import Skill, Category, SkillTag, SkillTagRelation
from app.models.enums import RiskLevel


class SkillRepository(BaseRepository[Skill]):
    """技能数据访问层"""

    model_class = Skill

    async def find_by_slug(self, slug: str) -> Optional[Skill]:
        """通过 slug 查找技能"""
        return await self.model_class.get_or_none(slug=slug).prefetch_related("category")

    async def find_by_category(
        self,
        category_slug: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Skill]:
        """按分类获取技能"""
        category = await Category.get_or_none(slug=category_slug)
        if not category:
            return []
        return await self.model_class.filter(
            category=category,
            is_blocked=False
        ).offset(skip).limit(limit).order_by("-created_at")

    async def find_safe_skills(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[Skill]:
        """获取安全技能（未阻止）"""
        return await self.model_class.filter(
            is_blocked=False,
            safe_to_publish=True
        ).offset(skip).limit(limit).order_by("-created_at")

    async def find_by_risk_level(
        self,
        risk_level: RiskLevel,
        skip: int = 0,
        limit: int = 100
    ) -> List[Skill]:
        """按风险等级获取技能"""
        return await self.model_class.filter(
            risk_level=risk_level
        ).offset(skip).limit(limit).order_by("-created_at")

    async def search(
        self,
        keyword: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Skill]:
        """搜索技能"""
        return await self.model_class.filter(
            is_blocked=False
        ).filter(
            name__icontains=keyword
        ).offset(skip).limit(limit).order_by("-created_at")

    async def get_skill_tags(self, skill: Skill) -> List[str]:
        """获取技能标签"""
        tag_relations = await SkillTagRelation.filter(skill=skill).prefetch_related("tag")
        return [tr.tag.name for tr in tag_relations]

    async def set_skill_tags(self, skill: Skill, tag_names: List[str]) -> None:
        """设置技能标签"""
        # 删除旧关联
        await SkillTagRelation.filter(skill=skill).delete()

        # 创建新关联
        for name in tag_names:
            tag, _ = await SkillTag.get_or_create(name=name)
            await SkillTagRelation.create(skill=skill, tag=tag)

    async def count_by_category(self, category_slug: str) -> int:
        """统计分类下技能数"""
        category = await Category.get_or_none(slug=category_slug)
        if not category:
            return 0
        return await self.model_class.filter(category=category).count()


class CategoryRepository(BaseRepository[Category]):
    """分类数据访问层"""

    model_class = Category

    async def find_by_slug(self, slug: str) -> Optional[Category]:
        """通过 slug 查找分类"""
        return await self.model_class.get_or_none(slug=slug)

    async def list_ordered(self) -> List[Category]:
        """获取排序后的分类列表"""
        return await self.model_class.all().order_by("sort_order")
