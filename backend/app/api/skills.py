from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from tortoise.functions import Count

from app.models.skill import Skill, Category, SkillTag, SkillTagRelation
from app.models.audit import SecurityAudit, SecurityFinding, RiskFactorEvidence
from app.models.content import (
    SkillContent, UseCase, PromptTemplate, OutputExample, FAQ
)
from app.models.enums import RiskLevel, SupportedTool
from app.schemas.skill import (
    SkillCreate, SkillUpdate, SkillOut, SkillDetailOut, SkillListOut,
    CategoryOut, TagOut
)
from app.config import settings

router = APIRouter(prefix="/skills", tags=["skills"])


# ============ 辅助函数 ============
async def get_or_create_tags(tag_names: List[str]) -> List[SkillTag]:
    """获取或创建标签"""
    tags = []
    for name in tag_names:
        tag, _ = await SkillTag.get_or_create(name=name)
        tags.append(tag)
    return tags


async def get_category_by_slug(slug: str) -> Optional[Category]:
    """通过 slug 获取分类"""
    if not slug:
        return None
    return await Category.get_or_none(slug=slug)


def skill_to_out(skill: Skill, tags: List[str] = None, category_slug: str = None) -> dict:
    """转换技能模型为输出格式"""
    return {
        "id": skill.id,
        "slug": skill.slug,
        "name": skill.name,
        "icon": skill.icon,
        "description": skill.description,
        "summary": skill.summary,
        "version": skill.version,
        "author": skill.author,
        "license": skill.license,
        "category": category_slug,
        "tags": tags or [],
        "supported_tools": skill.supported_tools or [],
        "risk_factors": skill.risk_factors or [],
        "risk_level": skill.risk_level,
        "is_blocked": skill.is_blocked,
        "safe_to_publish": skill.safe_to_publish,
        "source_url": skill.source_url,
        "source_type": skill.source_type,
        "generated_at": skill.generated_at,
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
    }


# ============ CRUD 接口 ============

@router.post("", response_model=SkillDetailOut, status_code=201)
async def create_skill(skill_data: SkillCreate):
    """创建技能"""
    # 检查 slug 是否已存在
    if await Skill.exists(slug=skill_data.slug):
        raise HTTPException(status_code=400, detail="Slug already exists")

    # 获取分类
    category = await get_category_by_slug(skill_data.category) if skill_data.category else None

    # 创建技能
    skill = await Skill.create(
        slug=skill_data.slug,
        name=skill_data.name,
        icon=skill_data.icon,
        description=skill_data.description,
        summary=skill_data.summary,
        version=skill_data.version,
        author=skill_data.author,
        license=skill_data.license,
        category=category,
        supported_tools=[t.value for t in skill_data.supported_tools],
        risk_factors=[r.value for r in skill_data.risk_factors],
        source_url=skill_data.source_url,
        source_type=skill_data.source_type,
        source_ref=skill_data.source_ref,
        seo_keywords=skill_data.seo_keywords,
    )

    # 处理标签
    tags = await get_or_create_tags(skill_data.tags)
    for tag in tags:
        await SkillTagRelation.create(skill=skill, tag=tag)

    # 创建安全审计
    if skill_data.audit:
        audit = await SecurityAudit.create(
            skill=skill,
            risk_level=skill_data.audit.risk_level,
            is_blocked=skill_data.audit.is_blocked,
            safe_to_publish=skill_data.audit.safe_to_publish,
            summary=skill_data.audit.summary,
            files_scanned=skill_data.audit.files_scanned,
            total_lines=skill_data.audit.total_lines,
            audit_model=skill_data.audit.audit_model,
            risk_factors=[r.value for r in skill_data.audit.risk_factors],
        )

        # 创建安全发现
        for finding in skill_data.audit.findings:
            await SecurityFinding.create(
                audit=audit,
                severity=finding.severity,
                title=finding.title,
                description=finding.description,
                locations=[loc.model_dump() for loc in finding.locations],
            )

        # 创建风险因素证据
        for evidence in skill_data.audit.risk_evidence:
            await RiskFactorEvidence.create(
                audit=audit,
                factor=evidence.factor,
                evidence=[loc.model_dump() for loc in evidence.evidence],
            )

        # 更新技能风险状态
        skill.risk_level = skill_data.audit.risk_level
        skill.is_blocked = skill_data.audit.is_blocked
        skill.safe_to_publish = skill_data.audit.safe_to_publish
        await skill.save()

    # 创建内容
    if skill_data.content:
        content = await SkillContent.create(
            skill=skill,
            user_title=skill_data.content.user_title,
            value_statement=skill_data.content.value_statement,
            actual_capabilities=skill_data.content.actual_capabilities,
            limitations=skill_data.content.limitations,
            best_practices=skill_data.content.best_practices,
            anti_patterns=skill_data.content.anti_patterns,
        )

        # 创建使用场景
        for uc in skill_data.content.use_cases:
            await UseCase.create(content=content, **uc.model_dump())

        # 创建提示词模板
        for pt in skill_data.content.prompt_templates:
            await PromptTemplate.create(content=content, **pt.model_dump())

        # 创建输出示例
        for oe in skill_data.content.output_examples:
            await OutputExample.create(
                content=content,
                input_text=oe.input_text,
                output_text=oe.output_text,
            )

        # 创建 FAQ
        for faq in skill_data.content.faq:
            await FAQ.create(content=content, **faq.model_dump())

    return await get_skill_detail(skill.slug)


@router.get("", response_model=SkillListOut)
async def list_skills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    risk_level: Optional[RiskLevel] = None,
    tool: Optional[SupportedTool] = None,
    search: Optional[str] = None,
    source_type: Optional[str] = None,
):
    """获取技能列表（支持分页和过滤）"""
    query = Skill.all()

    # 过滤条件
    if category:
        cat = await Category.get_or_none(slug=category)
        if cat:
            query = query.filter(category=cat)

    if risk_level:
        query = query.filter(risk_level=risk_level)

    if tool:
        query = query.filter(supported_tools__contains=tool.value)

    if source_type:
        query = query.filter(source_type=source_type)

    if search:
        query = query.filter(
            name__icontains=search
        ) | query.filter(
            description__icontains=search
        ) | query.filter(
            summary__icontains=search
        )

    # 排除被阻止的技能
    query = query.filter(is_blocked=False)

    # 计算总数
    total = await query.count()

    # 分页
    offset = (page - 1) * page_size
    skills = await query.offset(offset).limit(page_size).order_by("-created_at")

    # 构建输出
    items = []
    for skill in skills:
        # 获取标签
        tag_relations = await SkillTagRelation.filter(skill=skill).prefetch_related("tag")
        tags = [tr.tag.name for tr in tag_relations]

        # 获取分类 slug
        cat_slug = None
        if skill.category_id:
            cat = await Category.get_or_none(id=skill.category_id)
            cat_slug = cat.slug if cat else None

        item = skill_to_out(skill, tags, cat_slug)
        items.append(SkillOut(**item))

    total_pages = (total + page_size - 1) // page_size

    return SkillListOut(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{slug}", response_model=SkillDetailOut)
async def get_skill_detail(slug: str):
    """获取技能详情"""
    skill = await Skill.get_or_none(slug=slug).prefetch_related("category")
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # 获取标签
    tag_relations = await SkillTagRelation.filter(skill=skill).prefetch_related("tag")
    tags = [tr.tag.name for tr in tag_relations]

    # 构建基础输出
    cat_slug = skill.category.slug if skill.category else None
    base = skill_to_out(skill, tags, cat_slug)

    # 获取审计信息
    audit_out = None
    audit = await SecurityAudit.get_or_none(skill=skill)
    if audit:
        findings = await SecurityFinding.filter(audit=audit).all()
        risk_evidence = await RiskFactorEvidence.filter(audit=audit).all()

        audit_out = {
            "id": audit.id,
            "skill_id": audit.skill_id,
            "risk_level": audit.risk_level,
            "is_blocked": audit.is_blocked,
            "safe_to_publish": audit.safe_to_publish,
            "summary": audit.summary,
            "files_scanned": audit.files_scanned,
            "total_lines": audit.total_lines,
            "audit_model": audit.audit_model,
            "audited_at": audit.audited_at,
            "risk_factors": audit.risk_factors,
            "findings": [
                {
                    "id": f.id,
                    "severity": f.severity,
                    "title": f.title,
                    "description": f.description,
                    "locations": f.locations,
                }
                for f in findings
            ],
            "risk_evidence": [
                {
                    "id": e.id,
                    "factor": e.factor,
                    "evidence": e.evidence,
                }
                for e in risk_evidence
            ],
        }

    # 获取内容信息
    content_out = None
    content = await SkillContent.get_or_none(skill=skill)
    if content:
        use_cases = await UseCase.filter(content=content).all()
        prompt_templates = await PromptTemplate.filter(content=content).all()
        output_examples = await OutputExample.filter(content=content).all()
        faq = await FAQ.filter(content=content).all()

        content_out = {
            "id": content.id,
            "skill_id": content.skill_id,
            "user_title": content.user_title,
            "value_statement": content.value_statement,
            "actual_capabilities": content.actual_capabilities,
            "limitations": content.limitations,
            "best_practices": content.best_practices,
            "anti_patterns": content.anti_patterns,
            "use_cases": [
                {"id": uc.id, "title": uc.title, "description": uc.description, "target_user": uc.target_user}
                for uc in use_cases
            ],
            "prompt_templates": [
                {"id": pt.id, "title": pt.title, "scenario": pt.scenario, "prompt": pt.prompt}
                for pt in prompt_templates
            ],
            "output_examples": [
                {"id": oe.id, "input_text": oe.input_text, "output_text": oe.output_text}
                for oe in output_examples
            ],
            "faq": [
                {"id": f.id, "question": f.question, "answer": f.answer}
                for f in faq
            ],
        }

    return SkillDetailOut(
        **base,
        audit=audit_out,
        content=content_out,
    )


@router.patch("/{slug}", response_model=SkillOut)
async def update_skill(slug: str, skill_data: SkillUpdate):
    """更新技能"""
    skill = await Skill.get_or_none(slug=slug)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    update_data = skill_data.model_dump(exclude_unset=True)

    # 处理标签更新
    if "tags" in update_data:
        tags = await get_or_create_tags(update_data.pop("tags"))
        # 删除旧关联
        await SkillTagRelation.filter(skill=skill).delete()
        # 创建新关联
        for tag in tags:
            await SkillTagRelation.create(skill=skill, tag=tag)

    # 处理 supported_tools 和 risk_factors
    if "supported_tools" in update_data:
        update_data["supported_tools"] = [t.value if hasattr(t, 'value') else t for t in update_data["supported_tools"]]
    if "risk_factors" in update_data:
        update_data["risk_factors"] = [r.value if hasattr(r, 'value') else r for r in update_data["risk_factors"]]

    # 更新其他字段
    for field, value in update_data.items():
        setattr(skill, field, value)

    await skill.save()

    # 获取更新后的标签
    tag_relations = await SkillTagRelation.filter(skill=skill).prefetch_related("tag")
    tags = [tr.tag.name for tr in tag_relations]

    cat_slug = None
    if skill.category_id:
        cat = await Category.get_or_none(id=skill.category_id)
        cat_slug = cat.slug if cat else None

    result = skill_to_out(skill, tags, cat_slug)
    return SkillOut(**result)


@router.delete("/{slug}", status_code=204)
async def delete_skill(slug: str):
    """删除技能"""
    skill = await Skill.get_or_none(slug=slug)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    await skill.delete()
    return None


# ============ 分类接口 ============

@router.get("/categories/list", response_model=List[CategoryOut])
async def list_categories():
    """获取所有分类"""
    categories = await Category.all().order_by("sort_order")
    result = []
    for c in categories:
        skill_count = await Skill.filter(category=c).count()
        result.append(CategoryOut(
            id=c.id,
            slug=c.slug,
            name=c.name,
            description=c.description,
            icon=c.icon,
            skill_count=skill_count,
        ))
    return result


# ============ 标签接口 ============

@router.get("/tags/popular", response_model=List[TagOut])
async def get_popular_tags(limit: int = Query(20, ge=1, le=100)):
    """获取热门标签"""
    tags = await SkillTag.annotate(
        skill_count=Count("skill_relations")
    ).order_by("-skill_count").limit(limit)

    return [TagOut(name=t.name, count=t.skill_count) for t in tags]
