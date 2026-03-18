from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.enums import RiskLevel, Severity, RiskFactor


class RiskFactorEvidenceOut(BaseModel):
    """风险因素证据输出"""
    id: int
    factor: RiskFactor
    evidence: List[Dict[str, Any]]

    class Config:
        from_attributes = True


class RiskFactorEvidenceCreate(BaseModel):
    """创建风险因素证据"""
    factor: RiskFactor
    evidence: List[Dict[str, Any]] = Field(default_factory=list)


class SecurityFindingOut(BaseModel):
    """安全发现输出"""
    id: int
    severity: Severity
    title: str
    description: str
    locations: List[Dict[str, Any]]

    class Config:
        from_attributes = True


class SecurityFindingCreate(BaseModel):
    """创建安全发现"""
    severity: Severity
    title: str = Field(..., min_length=1, max_length=255)
    description: str
    locations: List[Dict[str, Any]] = Field(default_factory=list)


class SecurityAuditOut(BaseModel):
    """审计报告输出"""
    id: int
    risk_level: RiskLevel
    is_blocked: bool
    safe_to_publish: bool
    summary: str
    files_scanned: int
    total_lines: int
    risk_factors: List[RiskFactor]
    audited_at: datetime
    audit_model: Optional[str] = None

    class Config:
        from_attributes = True


class SecurityAuditCreate(BaseModel):
    """创建审计报告"""
    skill_id: int
    risk_level: RiskLevel = RiskLevel.SAFE
    is_blocked: bool = False
    safe_to_publish: bool = True
    summary: str
    files_scanned: int = 0
    total_lines: int = 0
    risk_factors: List[RiskFactor] = Field(default_factory=list)
    audit_model: Optional[str] = None
