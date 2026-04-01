from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from typing import Optional, List
from tortoise.functions import Count
from datetime import datetime
import zipfile
import io
import os

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
from app.core.exceptions import NotFoundError, ConflictError, ValidationError
from app.services.skill_loader import (
    load_skills_json, find_skill_by_slug, increment_download, validate_slug,
)

router = APIRouter(prefix="/skills", tags=["skills"])

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
SKILLS_DIR = os.path.join(_PROJECT_ROOT, "skills")


def _skill_item_to_out(item: dict, index: int) -> dict:
    """将 skills.json 单条记录转为 SkillOut 兼容 dict"""
    generated_at = item.get("generated_at")
    return {
        "id": index + 1,
        "slug": item["slug"],
        "name": item["name"],
        "icon": item.get("icon", "📦"),
        "description": item.get("description", item.get("summary", "")),
        "summary": item.get("summary"),
        "version": item.get("version", "1.0.0"),
        "author": item.get("author", ""),
        "license": item.get("license"),
        "category": item.get("category"),
        "tags": item.get("tags", []),
        "supported_tools": item.get("supported_tools", []),
        "risk_factors": item.get("risk_factors", []),
        "risk_level": item.get("risk_level", "safe"),
        "is_blocked": item.get("is_blocked", False),
        "safe_to_publish": item.get("safe_to_publish", True),
        "source_url": item.get("source_url", ""),
        "source_type": item.get("source_type", "community"),
        "generated_at": generated_at,
        "created_at": generated_at or datetime.now().isoformat(),
        "updated_at": generated_at or datetime.now().isoformat(),
    }


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
        raise ConflictError(message="Slug already exists", detail={"slug": skill_data.slug})

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
    """获取技能列表（支持分页和过滤）- 直接读取 skills.json"""
    all_skills = load_skills_json()

    # 在内存中过滤
    filtered = []
    for idx, item in enumerate(all_skills):
        # 排除被阻止的技能
        if item.get("is_blocked", False):
            continue
        if category and item.get("category") != category:
            continue
        if risk_level and item.get("risk_level") != risk_level.value:
            continue
        if tool and tool.value not in item.get("supported_tools", []):
            continue
        if source_type and item.get("source_type") != source_type:
            continue
        if search:
            s = search.lower()
            if (s not in item.get("name", "").lower()
                    and s not in item.get("description", "").lower()
                    and s not in item.get("summary", "").lower()):
                continue
        filtered.append((idx, item))

    total = len(filtered)
    offset = (page - 1) * page_size
    page_items = filtered[offset:offset + page_size]

    items = [SkillOut(**_skill_item_to_out(item, idx)) for idx, item in page_items]
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
    """获取技能详情 - 直接读取 skills.json"""
    all_skills = load_skills_json()

    skill_item = None
    skill_idx = -1
    for idx, item in enumerate(all_skills):
        if item.get("slug") == slug:
            skill_item = item
            skill_idx = idx
            break

    if skill_item is None:
        raise NotFoundError(message="Skill not found", detail={"slug": slug})

    base = _skill_item_to_out(skill_item, skill_idx)

    # 构建内容信息（skills.json 中有丰富数据时映射）
    content_out = None
    has_content = any(k in skill_item for k in (
        "user_title", "value_statement", "actual_capabilities",
        "use_cases", "prompt_templates", "limitations", "faq"
    ))
    if has_content:
        content_out = {
            "id": skill_idx + 1,
            "skill_id": skill_idx + 1,
            "user_title": skill_item.get("user_title"),
            "value_statement": skill_item.get("value_statement"),
            "actual_capabilities": skill_item.get("actual_capabilities", []),
            "limitations": skill_item.get("limitations", []),
            "best_practices": skill_item.get("best_practices", []),
            "anti_patterns": skill_item.get("anti_patterns", []),
            "use_cases": [
                {"id": i, "title": uc.get("title", ""), "description": uc.get("description", ""), "target_user": uc.get("target_user")}
                for i, uc in enumerate(skill_item.get("use_cases", []))
            ],
            "prompt_templates": [
                {"id": i, "title": pt.get("title", ""), "scenario": pt.get("scenario"), "prompt": pt.get("prompt", "")}
                for i, pt in enumerate(skill_item.get("prompt_templates", []))
            ],
            "output_examples": [
                {"id": i, "input_text": oe.get("input_text", ""), "output_text": oe.get("output_text", "")}
                for i, oe in enumerate(skill_item.get("output_examples", []))
            ],
            "faq": [
                {"id": i, "question": f.get("question", ""), "answer": f.get("answer", "")}
                for i, f in enumerate(skill_item.get("faq", []))
            ],
        }

    return SkillDetailOut(
        **base,
        audit=None,
        content=content_out,
    )


@router.patch("/{slug}", response_model=SkillOut)
async def update_skill(slug: str, skill_data: SkillUpdate):
    """更新技能"""
    skill = await Skill.get_or_none(slug=slug)
    if not skill:
        raise NotFoundError(message="Skill not found", detail={"slug": slug})

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
        raise NotFoundError(message="Skill not found", detail={"slug": slug})

    await skill.delete()
    return None


# ============ 分类接口 ============

@router.get("/categories/list", response_model=List[CategoryOut])
async def list_categories():
    """获取所有分类 - 从 skills.json 统计"""
    from collections import Counter
    all_skills = load_skills_json()

    # 统计分类分布
    cat_counter: Counter = Counter()
    for item in all_skills:
        if not item.get("is_blocked", False):
            cat_counter[item.get("category", "uncategorized")] += 1

    # 转为列表，按数量降序
    result = []
    for idx, (slug, count) in enumerate(cat_counter.most_common(), 1):
        cat_name = slug.replace("-", " ").replace("_", " ").title() if slug != "uncategorized" else "未分类"
        result.append(CategoryOut(
            id=idx,
            slug=slug,
            name=cat_name,
            description="",
            icon="📁",
            skill_count=count,
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


# ============ 下载接口 ============

@router.get("/{slug}/download")
async def download_skill(slug: str):
    """下载技能 ZIP 包"""
    if not validate_slug(slug):
        raise ValidationError(message="无效的技能标识", detail={"slug": slug})

    skill_dir = os.path.join(SKILLS_DIR, slug)

    if not os.path.isdir(skill_dir):
        raise NotFoundError(message="Skill directory not found", detail={"slug": slug})

    # 递增下载计数
    await increment_download(slug)

    # 创建内存中的 ZIP 文件
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(skill_dir):
            for file in files:
                file_path = os.path.join(root, file)
                # 保持相对路径结构，以技能名称为根目录
                arcname = os.path.relpath(file_path, SKILLS_DIR)
                zipf.write(file_path, arcname)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={slug}.zip"
        }
    )
