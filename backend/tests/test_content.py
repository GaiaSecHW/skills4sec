"""
Tests for content models
"""
import pytest

from app.models.skill import Skill
from app.models.content import (
    SkillContent, UseCase, PromptTemplate,
    OutputExample, FAQ
)


class TestSkillContent:
    """Test SkillContent model"""

    @pytest.mark.asyncio
    async def test_create_skill_content(self, test_skill: Skill):
        """Test creating skill content"""
        content = await SkillContent.create(
            skill=test_skill,
            user_title="My Custom Title",
            value_statement="This skill helps with testing",
            actual_capabilities=["test1", "test2"],
            limitations=["limit1"],
            best_practices=["practice1"],
            anti_patterns=["antipattern1"],
        )

        assert content.id is not None
        assert content.user_title == "My Custom Title"
        assert len(content.actual_capabilities) == 2

    @pytest.mark.asyncio
    async def test_skill_content_relation(self, test_skill: Skill):
        """Test skill content relation"""
        content = await SkillContent.create(
            skill=test_skill,
            value_statement="Test value",
        )

        assert content.skill_id == test_skill.id


class TestUseCase:
    """Test UseCase model"""

    @pytest.mark.asyncio
    async def test_create_use_case(self, test_skill: Skill):
        """Test creating a use case"""
        content = await SkillContent.create(skill=test_skill)
        use_case = await UseCase.create(
            content=content,
            title="Test Use Case",
            description="A test use case",
            target_user="developers",
        )

        assert use_case.id is not None
        assert use_case.title == "Test Use Case"


class TestPromptTemplate:
    """Test PromptTemplate model"""

    @pytest.mark.asyncio
    async def test_create_prompt_template(self, test_skill: Skill):
        """Test creating a prompt template"""
        content = await SkillContent.create(skill=test_skill)
        template = await PromptTemplate.create(
            content=content,
            title="Test Template",
            scenario="Testing scenario",
            prompt="This is a test prompt",
        )

        assert template.id is not None
        assert template.title == "Test Template"


class TestOutputExample:
    """Test OutputExample model"""

    @pytest.mark.asyncio
    async def test_create_output_example(self, test_skill: Skill):
        """Test creating an output example"""
        content = await SkillContent.create(skill=test_skill)
        example = await OutputExample.create(
            content=content,
            input_text="Test input",
            output_text=["Test output line 1", "Test output line 2"],
        )

        assert example.id is not None
        assert example.input_text == "Test input"
        assert len(example.output_text) == 2

    @pytest.mark.asyncio
    async def test_create_output_example_with_list(self, test_skill: Skill):
        """Test creating an output example with list output"""
        content = await SkillContent.create(skill=test_skill)
        example = await OutputExample.create(
            content=content,
            input_text="Test input",
            output_text=["Output 1", "Output 2", "Output 3"],
        )

        assert example.id is not None
        assert len(example.output_text) == 3


class TestFAQ:
    """Test FAQ model"""

    @pytest.mark.asyncio
    async def test_create_faq(self, test_skill: Skill):
        """Test creating a FAQ"""
        content = await SkillContent.create(skill=test_skill)
        faq = await FAQ.create(
            content=content,
            question="Test question?",
            answer="Test answer",
        )

        assert faq.id is not None
        assert faq.question == "Test question?"
