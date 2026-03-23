"""
Tests for Skill Repository - 技能仓库测试
"""
import pytest
from datetime import datetime

from app.repositories.skill_repository import SkillRepository
from app.models.skill import Skill, Category, SkillTag, SkillTagRelation


class TestSkillRepository:
    """Test skill repository"""

    @pytest.fixture
    async def setup_skills(self, db, test_category):
        """Setup test skills"""
        skill1 = await Skill.create(
            slug="repo-test-1",
            name="Repo Test 1",
            description="Test skill 1",
            author="Test Author",
            category=test_category,
            risk_level="safe",
            is_blocked=False,
            safe_to_publish=True,
            source_url="https://github.com/test/repo1",
            source_type="community",
        )
        skill2 = await Skill.create(
            slug="repo-test-2",
            name="Repo Test 2",
            description="Test skill 2",
            author="Test Author",
            category=test_category,
            risk_level="high",
            is_blocked=True,
            safe_to_publish=False,
            source_url="https://github.com/test/repo2",
            source_type="community",
        )
        return [skill1, skill2]

    @pytest.mark.asyncio
    async def test_find_by_slug(self, db, setup_skills):
        """Test finding skill by slug"""
        repo = SkillRepository()
        skill = await repo.find_by_slug("repo-test-1")

        assert skill is not None
        assert skill.name == "Repo Test 1"

    @pytest.mark.asyncio
    async def test_find_by_slug_not_found(self, db):
        """Test finding skill by non-existent slug - 边界值"""
        repo = SkillRepository()
        skill = await repo.find_by_slug("non-existent-slug")

        assert skill is None

    @pytest.mark.asyncio
    async def test_find_by_category(self, db, setup_skills, test_category):
        """Test finding skills by category slug"""
        repo = SkillRepository()
        skills = await repo.find_by_category(test_category.slug)

        assert len(skills) >= 1  # Only non-blocked skills

    @pytest.mark.asyncio
    async def test_find_by_category_with_pagination(self, db, setup_skills, test_category):
        """Test finding skills by category with pagination - 边界值"""
        repo = SkillRepository()
        skills = await repo.find_by_category(test_category.slug, skip=0, limit=1)

        assert len(skills) <= 1

    @pytest.mark.asyncio
    async def test_find_safe_skills(self, db, setup_skills):
        """Test finding safe skills"""
        repo = SkillRepository()
        skills = await repo.find_safe_skills()

        assert len(skills) >= 1
        for skill in skills:
            assert skill.safe_to_publish is True
            assert skill.is_blocked is False

    @pytest.mark.asyncio
    async def test_find_by_risk_level(self, db, setup_skills):
        """Test finding skills by risk level"""
        repo = SkillRepository()
        skills = await repo.find_by_risk_level("safe")

        assert len(skills) >= 1

    @pytest.mark.asyncio
    async def test_search(self, db, setup_skills):
        """Test searching skills"""
        repo = SkillRepository()
        skills = await repo.search("Repo Test")

        assert len(skills) >= 1

    @pytest.mark.asyncio
    async def test_search_empty(self, db):
        """Test searching with empty query - 边界值"""
        repo = SkillRepository()
        skills = await repo.search("")

        # Should return all or handle gracefully
        assert isinstance(skills, list)


class TestSkillRepositoryBoundary:
    """边界值测试"""

    @pytest.mark.asyncio
    async def test_search_special_characters(self, db):
        """Test search with special characters"""
        repo = SkillRepository()
        # Should not crash
        skills = await repo.search("<script>alert('xss')</script>")
        assert isinstance(skills, list)

    @pytest.mark.asyncio
    async def test_search_sql_injection(self, db):
        """Test search with SQL injection attempt"""
        repo = SkillRepository()
        # Should not crash or inject
        skills = await repo.search("'; DROP TABLE skills; --")
        assert isinstance(skills, list)

    @pytest.mark.asyncio
    async def test_pagination_large_skip(self, db):
        """Test pagination with large skip value"""
        repo = SkillRepository()
        skills = await repo.list_all(skip=99999, limit=10)
        assert len(skills) == 0

    @pytest.mark.asyncio
    async def test_pagination_zero_limit(self, db):
        """Test pagination with zero limit"""
        repo = SkillRepository()
        skills = await repo.list_all(skip=0, limit=0)
        assert len(skills) == 0

    @pytest.mark.asyncio
    async def test_find_by_category_nonexistent(self, db):
        """Test finding by non-existent category - 边界值"""
        repo = SkillRepository()
        skills = await repo.find_by_category("non-existent-slug")
        assert len(skills) == 0
