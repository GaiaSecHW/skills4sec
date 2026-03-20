"""
Tests for model methods and utilities
"""
import pytest

from app.models.enums import RiskLevel, SourceType, Severity, RiskFactor, SupportedTool
from app.models.skill import Category, Skill, SkillTag, SkillTagRelation


class TestEnums:
    """Test enum values"""

    def test_risk_level_values(self):
        """Test RiskLevel enum values"""
        assert RiskLevel.SAFE.value == "safe"
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_source_type_values(self):
        """Test SourceType enum values"""
        assert SourceType.COMMUNITY.value == "community"
        assert SourceType.OFFICIAL.value == "official"

    def test_severity_values(self):
        """Test Severity enum values"""
        assert Severity.INFO.value == "info"
        assert Severity.LOW.value == "low"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.HIGH.value == "high"
        assert Severity.CRITICAL.value == "critical"

    def test_risk_factor_values(self):
        """Test RiskFactor enum values"""
        assert RiskFactor.SCRIPTS.value == "scripts"
        assert RiskFactor.NETWORK.value == "network"
        assert RiskFactor.FILESYSTEM.value == "filesystem"
        assert RiskFactor.ENV_ACCESS.value == "env_access"
        assert RiskFactor.EXTERNAL_COMMANDS.value == "external_commands"
        assert RiskFactor.CLOUD_API.value == "cloud_api"
        assert RiskFactor.IAM.value == "iam"

    def test_supported_tool_values(self):
        """Test SupportedTool enum values"""
        assert SupportedTool.CLAUDE.value == "claude"
        assert SupportedTool.CODEX.value == "codex"
        assert SupportedTool.CLAUDE_CODE.value == "claude-code"


class TestCategoryModel:
    """Test Category model"""

    @pytest.mark.asyncio
    async def test_category_str(self, test_category):
        """Test Category string representation"""
        assert str(test_category) == "Test Category"

    @pytest.mark.asyncio
    async def test_category_create(self, db):
        """Test creating a category"""
        category = await Category.create(
            slug="new-cat",
            name="New Category",
            description="A new category",
            sort_order=10,
        )

        assert category.id is not None
        assert category.slug == "new-cat"
        assert category.name == "New Category"


class TestSkillModel:
    """Test Skill model"""

    @pytest.mark.asyncio
    async def test_skill_str(self, test_skill):
        """Test Skill string representation"""
        assert "Test Skill" in str(test_skill)

    @pytest.mark.asyncio
    async def test_skill_create_with_defaults(self, db):
        """Test creating a skill with default values"""
        skill = await Skill.create(
            slug="default-skill",
            name="Default Skill",
            description="A skill with defaults",
            author="Test Author",
            source_url="https://github.com/test/default",
        )

        assert skill.risk_level == RiskLevel.SAFE
        assert skill.is_blocked is False
        assert skill.safe_to_publish is True
        assert skill.supported_tools == []
        assert skill.risk_factors == []

    @pytest.mark.asyncio
    async def test_skill_create_with_category(self, db, test_category):
        """Test creating a skill with category"""
        skill = await Skill.create(
            slug="categorized-skill",
            name="Categorized Skill",
            description="A categorized skill",
            author="Test Author",
            source_url="https://github.com/test/categorized",
            category=test_category,
        )

        assert skill.category_id == test_category.id


class TestSkillTag:
    """Test SkillTag model"""

    @pytest.mark.asyncio
    async def test_skill_tag_create(self, db):
        """Test creating a skill tag"""
        tag = await SkillTag.create(name="python")

        assert tag.id is not None
        assert tag.name == "python"

    @pytest.mark.asyncio
    async def test_skill_tag_unique(self, db):
        """Test skill tag uniqueness"""
        await SkillTag.create(name="unique-tag")

        with pytest.raises(Exception):  # IntegrityError
            await SkillTag.create(name="unique-tag")


class TestSkillTagRelation:
    """Test SkillTagRelation model"""

    @pytest.mark.asyncio
    async def test_skill_tag_relation(self, db, test_skill):
        """Test creating skill-tag relation"""
        tag = await SkillTag.create(name="test-tag")
        relation = await SkillTagRelation.create(skill=test_skill, tag=tag)

        assert relation.skill_id == test_skill.id
        assert relation.tag_id == tag.id
