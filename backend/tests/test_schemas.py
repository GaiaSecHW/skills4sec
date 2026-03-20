"""
Tests for schema validation
"""
import pytest
from pydantic import ValidationError

from app.schemas.user import (
    UserLoginByEmployeeId, TokenWithRefresh, TokenRefresh,
    UserOutNew
)
from app.schemas.skill import (
    SkillCreate, SkillUpdate, SkillOut
)
from app.schemas.audit import (
    SecurityAuditCreate, SecurityFindingCreate
)


class TestUserSchemas:
    """Test user schemas"""

    def test_user_login_schema(self):
        """Test UserLoginByEmployeeId schema"""
        data = UserLoginByEmployeeId(
            employee_id="TEST001",
            api_key="test-api-key"
        )
        assert data.employee_id == "TEST001"
        assert data.api_key == "test-api-key"

    def test_token_refresh_schema(self):
        """Test TokenRefresh schema"""
        data = TokenRefresh(refresh_token="test-token")
        assert data.refresh_token == "test-token"

    def test_user_out_schema(self):
        """Test UserOutNew schema"""
        data = UserOutNew(
            id=1,
            employee_id="TEST001",
            name="Test User",
            role="user",
            status="active",
            is_active=True,
            is_superuser=False,
            department="Engineering",
            team="Backend",
            group_name="Developers",
            skills_count=0,
            last_login=None,
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        assert data.id == 1
        assert data.employee_id == "TEST001"


class TestSkillSchemas:
    """Test skill schemas"""

    def test_skill_create_minimal(self):
        """Test SkillCreate with minimal data"""
        data = SkillCreate(
            slug="test-skill",
            name="Test Skill",
            description="A test skill",
            author="Test Author",
            source_url="https://github.com/test/skill",
        )
        assert data.slug == "test-skill"
        assert data.name == "Test Skill"

    def test_skill_update_partial(self):
        """Test SkillUpdate with partial data"""
        data = SkillUpdate(name="Updated Name")
        assert data.name == "Updated Name"

    def test_skill_update_empty(self):
        """Test SkillUpdate can be empty"""
        data = SkillUpdate()
        assert data.name is None


class TestAuditSchemas:
    """Test audit schemas"""

    def test_audit_create(self):
        """Test SecurityAuditCreate schema"""
        data = SecurityAuditCreate(
            skill_id=1,
            risk_level="safe",
            is_blocked=False,
            safe_to_publish=True,
            summary="Test audit",
            audit_model="test-model",
        )
        assert data.skill_id == 1
        assert data.risk_level == "safe"

    def test_finding_create(self):
        """Test SecurityFindingCreate schema"""
        data = SecurityFindingCreate(
            severity="high",
            title="Test Finding",
            description="A test finding",
            locations=[],
        )
        assert data.severity == "high"
        assert data.title == "Test Finding"
