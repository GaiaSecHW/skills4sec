"""
Tests for audit models
"""
import pytest

from app.models.skill import Skill
from app.models.audit import SecurityAudit, SecurityFinding, RiskFactorEvidence
from app.models.enums import Severity


class TestSecurityFinding:
    """Test SecurityFinding model"""

    @pytest.mark.asyncio
    async def test_create_finding(self, test_skill: Skill):
        """Test creating a security finding"""
        audit = await SecurityAudit.create(
            skill=test_skill,
            risk_level="medium",
            is_blocked=False,
            safe_to_publish=True,
            summary="Test audit",
            audit_model="test-model",
        )

        finding = await SecurityFinding.create(
            audit=audit,
            severity=Severity.HIGH,
            title="Test Finding",
            description="A test finding",
            locations=[{"file": "test.py", "line": 10}],
        )

        assert finding.id is not None
        assert finding.severity == Severity.HIGH
        assert finding.title == "Test Finding"

    @pytest.mark.asyncio
    async def test_finding_with_locations(self, test_skill: Skill):
        """Test finding with multiple locations"""
        audit = await SecurityAudit.create(
            skill=test_skill,
            risk_level="low",
            is_blocked=False,
            safe_to_publish=True,
            summary="Test",
            audit_model="test",
        )

        finding = await SecurityFinding.create(
            audit=audit,
            severity=Severity.INFO,
            title="Multi-location finding",
            description="Found in multiple files",
            locations=[
                {"file": "a.py", "line": 1},
                {"file": "b.py", "line": 2},
            ],
        )

        assert len(finding.locations) == 2


class TestRiskFactorEvidence:
    """Test RiskFactorEvidence model"""

    @pytest.mark.asyncio
    async def test_create_evidence(self, test_skill: Skill):
        """Test creating risk factor evidence"""
        audit = await SecurityAudit.create(
            skill=test_skill,
            risk_level="high",
            is_blocked=True,
            safe_to_publish=False,
            summary="Risky",
            audit_model="test",
        )

        evidence = await RiskFactorEvidence.create(
            audit=audit,
            factor="network",
            evidence=[
                {"file": "network.py", "line": 10, "code": "requests.get()"}
            ],
        )

        assert evidence.id is not None
        assert evidence.factor == "network"
        assert len(evidence.evidence) == 1
