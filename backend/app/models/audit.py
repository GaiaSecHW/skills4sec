from tortoise import fields
from tortoise.models import Model
from app.models.enums import RiskLevel, Severity, RiskFactor


class SecurityAudit(Model):
    """安全审计报告"""
    id = fields.IntField(pk=True)
    skill = fields.OneToOneField(
        "models.Skill", related_name="audit", on_delete=fields.CASCADE
    )

    # 风险评估
    risk_level = fields.CharEnumField(RiskLevel, default=RiskLevel.SAFE)
    is_blocked = fields.BooleanField(default=False)
    safe_to_publish = fields.BooleanField(default=True)
    summary = fields.TextField(description="审计摘要")

    # 扫描统计
    files_scanned = fields.IntField(default=0, description="扫描文件数")
    total_lines = fields.IntField(default=0, description="总代码行数")

    # 审计元信息
    audit_model = fields.CharField(max_length=64, description="审计AI模型")
    audited_at = fields.DatetimeField(auto_now_add=True, description="审计时间")

    # 风险因素
    risk_factors = fields.JSONField(default=list, description="检测到的风险因素")

    class Meta:
        table = "security_audits"


class SecurityFinding(Model):
    """安全发现"""
    id = fields.IntField(pk=True)
    audit = fields.ForeignKeyField(
        "models.SecurityAudit", related_name="findings", on_delete=fields.CASCADE
    )

    severity = fields.CharEnumField(Severity, description="严重程度")
    title = fields.CharField(max_length=255, description="发现标题")
    description = fields.TextField(description="详细描述")
    locations = fields.JSONField(
        default=list, description="位置列表: [{file, line_start, line_end}]"
    )

    class Meta:
        table = "security_findings"


class RiskFactorEvidence(Model):
    """风险因素证据"""
    id = fields.IntField(pk=True)
    audit = fields.ForeignKeyField(
        "models.SecurityAudit", related_name="risk_evidence", on_delete=fields.CASCADE
    )

    factor = fields.CharEnumField(RiskFactor, description="风险因素类型")
    evidence = fields.JSONField(
        default=list, description="证据列表: [{file, line_start, line_end}]"
    )

    class Meta:
        table = "risk_factor_evidence"
