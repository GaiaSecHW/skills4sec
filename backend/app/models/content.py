from tortoise import fields
from tortoise.models import Model


class SkillContent(Model):
    """技能内容详情"""
    id = fields.IntField(pk=True)
    skill = fields.OneToOneField(
        "models.Skill", related_name="content", on_delete=fields.CASCADE
    )

    # 用户友好的标题
    user_title = fields.CharField(max_length=255, null=True, description="营销标题")
    value_statement = fields.TextField(null=True, description="价值陈述")

    # 能力与限制
    actual_capabilities = fields.JSONField(default=list, description="实际能力列表")
    limitations = fields.JSONField(default=list, description="已知限制")

    # 最佳实践与反模式
    best_practices = fields.JSONField(default=list)
    anti_patterns = fields.JSONField(default=list)

    class Meta:
        table = "skill_contents"


class UseCase(Model):
    """使用场景"""
    id = fields.IntField(pk=True)
    content = fields.ForeignKeyField(
        "models.SkillContent", related_name="use_cases", on_delete=fields.CASCADE
    )

    title = fields.CharField(max_length=255)
    description = fields.TextField()
    target_user = fields.CharField(max_length=128, null=True, description="目标用户")

    class Meta:
        table = "use_cases"


class PromptTemplate(Model):
    """提示词模板"""
    id = fields.IntField(pk=True)
    content = fields.ForeignKeyField(
        "models.SkillContent", related_name="prompt_templates", on_delete=fields.CASCADE
    )

    title = fields.CharField(max_length=255)
    scenario = fields.CharField(max_length=255, null=True, description="使用场景")
    prompt = fields.TextField(description="提示词内容")

    class Meta:
        table = "prompt_templates"


class OutputExample(Model):
    """输出示例"""
    id = fields.IntField(pk=True)
    content = fields.ForeignKeyField(
        "models.SkillContent", related_name="output_examples", on_delete=fields.CASCADE
    )

    input_text = fields.TextField(description="输入示例")
    output_text = fields.JSONField(description="输出示例 (字符串或数组)")

    class Meta:
        table = "output_examples"


class FAQ(Model):
    """常见问题"""
    id = fields.IntField(pk=True)
    content = fields.ForeignKeyField(
        "models.SkillContent", related_name="faq", on_delete=fields.CASCADE
    )

    question = fields.CharField(max_length=512)
    answer = fields.TextField()

    class Meta:
        table = "faqs"
