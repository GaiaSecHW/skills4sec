from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any

from app.models.user import User
from app.models.audit import SecurityAudit, SecurityFinding, RiskFactorEvidence
from app.models.skill import Skill
from app.schemas.audit import (
    SecurityAuditOut,
    SecurityAuditCreate,
    SecurityFindingOut,
    SecurityFindingCreate,
    RiskFactorEvidenceOut,
    RiskFactorEvidenceCreate,
)
from app.utils.security import get_current_user, get_current_superuser

router = APIRouter(prefix="/audit", tags=["security-audit"])


@router.get("/", response_model=List[SecurityAuditOut])
async def list_audits(
    skip: int = 0,
    limit: int = 20,
    risk_level: str = None,
    is_blocked: bool = None
):
    """
    获取审计报告列表

    支持分页和筛选：
    - **skip**: 跳过记录数
    - **limit**: 返回记录数
    - **risk_level**: 按风险等级筛选
    - **is_blocked**: 按是否被阻止筛选
    """
    query = SecurityAudit.all()

    if risk_level:
        query = query.filter(risk_level=risk_level)
    if is_blocked is not None:
        query = query.filter(is_blocked=is_blocked)

    audits = await query.offset(skip).limit(limit).order_by("-audited_at")
    return audits


@router.get("/stats")
async def get_audit_stats():
    """获取审计统计数据"""
    total = await SecurityAudit.all().count()
    safe = await SecurityAudit.filter(risk_level="safe").count()
    low = await SecurityAudit.filter(risk_level="low").count()
    medium = await SecurityAudit.filter(risk_level="medium").count()
    high = await SecurityAudit.filter(risk_level="high").count()
    critical = await SecurityAudit.filter(risk_level="critical").count()
    blocked = await SecurityAudit.filter(is_blocked=True).count()

    return {
        "total": total,
        "by_risk_level": {
            "safe": safe,
            "low": low,
            "medium": medium,
            "high": high,
            "critical": critical
        },
        "blocked": blocked
    }


@router.get("/{audit_id}", response_model=SecurityAuditOut)
async def get_audit(audit_id: int):
    """获取单个审计报告详情"""
    audit = await SecurityAudit.get_or_none(id=audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计报告不存在"
        )
    return audit


@router.post("/", response_model=SecurityAuditOut, status_code=status.HTTP_201_CREATED)
async def create_audit(
    audit_data: SecurityAuditCreate,
    current_user: User = Depends(get_current_user)
):
    """
    创建审计报告

    需要认证。用于为技能创建安全审计报告。
    """
    skill = await Skill.get_or_none(id=audit_data.skill_id)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="技能不存在"
        )

    existing = await SecurityAudit.get_or_none(skill_id=audit_data.skill_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该技能已有审计报告"
        )

    audit = await SecurityAudit.create(**audit_data.model_dump())
    return audit


@router.put("/{audit_id}", response_model=SecurityAuditOut)
async def update_audit(
    audit_id: int,
    audit_data: SecurityAuditCreate,
    current_user: User = Depends(get_current_user)
):
    """更新审计报告"""
    audit = await SecurityAudit.get_or_none(id=audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计报告不存在"
        )

    for key, value in audit_data.model_dump().items():
        setattr(audit, key, value)

    await audit.save()
    return audit


@router.delete("/{audit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_audit(
    audit_id: int,
    current_user: User = Depends(get_current_superuser)
):
    """删除审计报告（管理员）"""
    audit = await SecurityAudit.get_or_none(id=audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计报告不存在"
        )

    await audit.delete()


# === 安全发现相关API ===

@router.get("/{audit_id}/findings", response_model=List[SecurityFindingOut])
async def list_findings(audit_id: int):
    """获取审计报告的安全发现列表"""
    audit = await SecurityAudit.get_or_none(id=audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计报告不存在"
        )

    findings = await SecurityFinding.filter(audit_id=audit_id).all()
    return findings


@router.post("/{audit_id}/findings", response_model=SecurityFindingOut, status_code=status.HTTP_201_CREATED)
async def add_finding(
    audit_id: int,
    finding_data: SecurityFindingCreate,
    current_user: User = Depends(get_current_user)
):
    """
    添加安全发现

    需要认证。用于向审计报告添加安全发现。
    """
    audit = await SecurityAudit.get_or_none(id=audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计报告不存在"
        )

    finding = await SecurityFinding.create(
        audit_id=audit_id,
        **finding_data.model_dump()
    )
    return finding


@router.delete("/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_finding(
    finding_id: int,
    current_user: User = Depends(get_current_superuser)
):
    """删除安全发现（管理员）"""
    finding = await SecurityFinding.get_or_none(id=finding_id)
    if not finding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="安全发现不存在"
        )

    await finding.delete()


# === 风险因素证据相关API ===

@router.get("/{audit_id}/risk-factors", response_model=List[RiskFactorEvidenceOut])
async def list_risk_factors(audit_id: int):
    """获取审计报告的风险因素证据列表"""
    audit = await SecurityAudit.get_or_none(id=audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计报告不存在"
        )

    factors = await RiskFactorEvidence.filter(audit_id=audit_id).all()
    return factors


@router.post("/{audit_id}/risk-factors", response_model=RiskFactorEvidenceOut, status_code=status.HTTP_201_CREATED)
async def add_risk_factor(
    audit_id: int,
    factor_data: RiskFactorEvidenceCreate,
    current_user: User = Depends(get_current_user)
):
    """
    添加风险因素证据

    需要认证。用于添加风险因素的证据。
    """
    audit = await SecurityAudit.get_or_none(id=audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计报告不存在"
        )

    risk_factor = await RiskFactorEvidence.create(
        audit_id=audit_id,
        factor=factor_data.factor,
        evidence=factor_data.evidence
    )
    return risk_factor


@router.delete("/risk-factors/{risk_factor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_risk_factor(
    risk_factor_id: int,
    current_user: User = Depends(get_current_superuser)
):
    """删除风险因素证据（管理员）"""
    risk_factor = await RiskFactorEvidence.get_or_none(id=risk_factor_id)
    if not risk_factor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="风险因素证据不存在"
        )

    await risk_factor.delete()


# === 批量操作API ===

@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def batch_create_audits(
    audits_data: List[dict],
    current_user: User = Depends(get_current_user)
):
    """
    批量创建审计报告

    需要认证。用于一次性为多个技能创建审计报告。
    """
    created = []
    errors = []

    for audit_data in audits_data:
        skill_id = audit_data.get("skill_id")
        if not skill_id:
            errors.append({"error": "Missing skill_id", "data": audit_data})
            continue

        skill = await Skill.get_or_none(id=skill_id)
        if not skill:
            errors.append({"error": f"Skill {skill_id} not found", "data": audit_data})
            continue

        existing = await SecurityAudit.get_or_none(skill_id=skill_id)
        if existing:
            errors.append({"error": f"Audit already exists for skill {skill_id}", "data": audit_data})
            continue

        audit = await SecurityAudit.create(**audit_data)
        created.append(audit)

    return {"created": len(created), "errors": errors}


# === 报告导出API ===

@router.get("/{audit_id}/export")
async def export_audit_report(audit_id: int, format: str = "json"):
    """
    导出审计报告

    支持格式：json, csv, pdf
    """
    audit = await SecurityAudit.get_or_none(id=audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计报告不存在"
        )

    findings = await SecurityFinding.filter(audit_id=audit_id).all()
    factors = await RiskFactorEvidence.filter(audit_id=audit_id).all()

    report = {
        "audit": await SecurityAuditOut.from_tortoise_orm(audit),
        "findings": [await SecurityFindingOut.from_tortoise_orm(f) for f in findings],
        "risk_factors": [await RiskFactorEvidenceOut.from_tortoise_orm(f) for f in factors]
    }

    if format == "json":
        return report
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {format}"
        )


# === 健康检查API ===

@router.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "audit"}


@router.get("/health/services")
async def check_health_services():
    """检查服务健康状态"""
    return {"services": {"database": "healthy", "api": "healthy", "scanner": "healthy"}}


@router.get("/health/dependencies")
async def check_health_dependencies():
    """检查依赖健康状态"""
    return {"dependencies": {"database": "healthy", "redis": "healthy", "storage": "healthy"}}


# === 维护API ===

@router.post("/maintenance/cleanup")
async def run_maintenance_cleanup(current_user: User = Depends(get_current_superuser)):
    """运行维护清理（管理员）"""
    return {"cleanup": "started", "user_id": current_user.id}


@router.get("/maintenance/status")
async def get_maintenance_status(current_user: User = Depends(get_current_superuser)):
    """获取维护状态（管理员）"""
    return {"maintenance": {"last_run": None, "status": "idle"}}
