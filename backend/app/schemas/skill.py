from pydantic import BaseModel, Field
from typing import List, Optional, Union
from datetime import datetime
from app.models.enums import RiskLevel, SourceType, SupportedTool, RiskFactor, Severity


# ============ 位置信息 ============
class Location(BaseModel):
    file: str
    line_start: int
    line_end: int


# ============ 安全发现 ============
class SecurityFindingBase(BaseModel):
    severity: Severity
    title: str
    description: str
    locations: List[Location] = []


class SecurityFindingCreate(SecurityFindingBase):
    pass


class SecurityFindingOut(SecurityFindingBase):
    id: int

    class Config:
        from_attributes = True


# ============ 风险因素证据 ============
class RiskFactorEvidenceBase(BaseModel):
    factor: RiskFactor
    evidence: List[Location] = []


class RiskFactorEvidenceOut(RiskFactorEvidenceBase):
    id: int

    class Config:
        from_attributes = True


# ============ 安全审计 ============
class SecurityAuditBase(BaseModel):
    risk_level: RiskLevel = RiskLevel.SAFE
    is_blocked: bool = False
    safe_to_publish: bool = True
    summary: str
    files_scanned: int = 0
    total_lines: int = 0
    audit_model: str
    risk_factors: List[RiskFactor] = []


class SecurityAuditCreate(SecurityAuditBase):
    findings: List[SecurityFindingCreate] = []
    risk_evidence: List[RiskFactorEvidenceBase] = []


class SecurityAuditOut(SecurityAuditBase):
    id: int
    skill_id: int
    audited_at: datetime
    findings: List[SecurityFindingOut] = []
    risk_evidence: List[RiskFactorEvidenceOut] = []

    class Config:
        from_attributes = True


# ============ 使用场景 ============
class UseCaseBase(BaseModel):
    title: str
    description: str
    target_user: Optional[str] = None


class UseCaseCreate(UseCaseBase):
    pass


class UseCaseOut(UseCaseBase):
    id: int

    class Config:
        from_attributes = True


# ============ 提示词模板 ============
class PromptTemplateBase(BaseModel):
    title: str
    scenario: Optional[str] = None
    prompt: str


class PromptTemplateCreate(PromptTemplateBase):
    pass


class PromptTemplateOut(PromptTemplateBase):
    id: int

    class Config:
        from_attributes = True


# ============ 输出示例 ============
class OutputExampleBase(BaseModel):
    input_text: str
    output_text: Union[str, List[str]]


class OutputExampleCreate(OutputExampleBase):
    pass


class OutputExampleOut(OutputExampleBase):
    id: int

    class Config:
        from_attributes = True


# ============ FAQ ============
class FAQBase(BaseModel):
    question: str
    answer: str


class FAQCreate(FAQBase):
    pass


class FAQOut(FAQBase):
    id: int

    class Config:
        from_attributes = True


# ============ 技能内容 ============
class SkillContentBase(BaseModel):
    user_title: Optional[str] = None
    value_statement: Optional[str] = None
    actual_capabilities: List[str] = []
    limitations: List[str] = []
    best_practices: List[str] = []
    anti_patterns: List[str] = []


class SkillContentCreate(SkillContentBase):
    use_cases: List[UseCaseCreate] = []
    prompt_templates: List[PromptTemplateCreate] = []
    output_examples: List[OutputExampleCreate] = []
    faq: List[FAQCreate] = []


class SkillContentOut(SkillContentBase):
    id: int
    skill_id: int
    use_cases: List[UseCaseOut] = []
    prompt_templates: List[PromptTemplateOut] = []
    output_examples: List[OutputExampleOut] = []
    faq: List[FAQOut] = []

    class Config:
        from_attributes = True


# ============ 技能 ============
class SkillBase(BaseModel):
    slug: str = Field(..., pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
    name: str
    icon: str = "📦"
    description: str
    summary: Optional[str] = None
    version: str = "1.0.0"
    author: str
    license: Optional[str] = None
    category: Optional[str] = None  # category slug
    tags: List[str] = []
    supported_tools: List[SupportedTool] = [SupportedTool.CLAUDE_CODE]
    risk_factors: List[RiskFactor] = []
    source_url: str
    source_type: SourceType = SourceType.COMMUNITY
    source_ref: Optional[str] = None
    seo_keywords: List[str] = []


class SkillCreate(SkillBase):
    """创建技能请求"""
    audit: Optional[SecurityAuditCreate] = None
    content: Optional[SkillContentCreate] = None


class SkillUpdate(BaseModel):
    """更新技能请求"""
    name: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None
    version: Optional[str] = None
    tags: Optional[List[str]] = None
    supported_tools: Optional[List[SupportedTool]] = None
    risk_factors: Optional[List[RiskFactor]] = None
    seo_keywords: Optional[List[str]] = None


class SkillOut(BaseModel):
    """技能输出"""
    id: int
    slug: str
    name: str
    icon: str
    description: str
    summary: Optional[str]
    version: str
    author: str
    license: Optional[str]
    category: Optional[str]  # category slug
    tags: List[str] = []
    supported_tools: List[str] = []
    risk_factors: List[str] = []
    risk_level: RiskLevel
    is_blocked: bool
    safe_to_publish: bool
    source_url: str
    source_type: SourceType
    generated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SkillDetailOut(SkillOut):
    """技能详情输出（包含审计和内容）"""
    audit: Optional[SecurityAuditOut] = None
    content: Optional[SkillContentOut] = None


class SkillListOut(BaseModel):
    """技能列表分页输出"""
    items: List[SkillOut]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============ 分类 ============
class CategoryBase(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryOut(CategoryBase):
    id: int
    skill_count: int = 0

    class Config:
        from_attributes = True


# ============ 标签 ============
class TagOut(BaseModel):
    name: str
    count: int = 0


# ============ 统计排行 ============
class RankingItem(BaseModel):
    """排行项"""
    rank: int
    skill_name: str
    downloads: int
    author: str


class StatsPeriod(BaseModel):
    """统计周期"""
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class TopStatsOut(BaseModel):
    """下载排行统计响应"""
    period: StatsPeriod
    total_downloads: int
    rankings: List[RankingItem]
