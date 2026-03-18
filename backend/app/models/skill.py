from tortoise import fields
from tortoise.models import Model
from app.models.enums import RiskLevel, SourceType


class Category(Model):
    """技能分类"""
    id = fields.IntField(pk=True)
    slug = fields.CharField(max_length=64, unique=True, description="分类标识")
    name = fields.CharField(max_length=128, description="分类名称")
    description = fields.TextField(null=True, description="分类描述")
    icon = fields.CharField(max_length=10, null=True, description="图标")
    sort_order = fields.IntField(default=0, description="排序")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "categories"

    def __str__(self):
        return self.name


class SkillTag(Model):
    """技能标签"""
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=64, unique=True)

    class Meta:
        table = "skill_tags"

    def __str__(self):
        return self.name


class Skill(Model):
    """技能主表"""
    id = fields.IntField(pk=True)
    slug = fields.CharField(max_length=128, unique=True, index=True, description="唯一标识")
    name = fields.CharField(max_length=255, description="显示名称")
    icon = fields.CharField(max_length=10, default="📦", description="emoji图标")

    # 描述信息
    description = fields.TextField(description="详细描述")
    summary = fields.TextField(null=True, description="简短摘要")

    # 版本与作者
    version = fields.CharField(max_length=32, default="1.0.0")
    author = fields.CharField(max_length=128)
    license = fields.CharField(max_length=64, null=True)

    # 分类关联
    category = fields.ForeignKeyField(
        "models.Category", related_name="skills", null=True
    )

    # 支持的工具 (存储为 JSON 数组)
    supported_tools = fields.JSONField(
        default=list,
        description="支持的AI工具: claude, codex, claude-code"
    )

    # 风险评估
    risk_factors = fields.JSONField(default=list, description="风险因素标签")
    risk_level = fields.CharEnumField(RiskLevel, default=RiskLevel.SAFE)
    is_blocked = fields.BooleanField(default=False, description="是否被阻止发布")
    safe_to_publish = fields.BooleanField(default=True, description="是否安全发布")

    # 来源信息
    source_url = fields.CharField(max_length=512, description="GitHub源地址")
    source_type = fields.CharEnumField(SourceType, default=SourceType.COMMUNITY)
    source_ref = fields.CharField(max_length=64, null=True, description="Git分支或标签")

    # SEO
    seo_keywords = fields.JSONField(default=list, description="SEO关键词")

    # 时间戳
    generated_at = fields.DatetimeField(null=True, description="生成时间")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "skills"
        indexes = [("slug",), ("risk_level",), ("category_id",)]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class SkillTagRelation(Model):
    """技能-标签多对多关系"""
    skill = fields.ForeignKeyField("models.Skill", related_name="tag_relations")
    tag = fields.ForeignKeyField("models.SkillTag", related_name="skill_relations")

    class Meta:
        table = "skill_tag_relations"
        unique_together = ("skill", "tag")
