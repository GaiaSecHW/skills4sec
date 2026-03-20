"""
Tests for submission model
"""
import pytest
from datetime import datetime

from app.models.submission import (
    Submission, SubmissionEvent, SubmissionStatus, SubmissionEventType
)


class TestSubmissionModel:
    """Test Submission model"""

    @pytest.mark.asyncio
    async def test_create_submission(self, db):
        """Test creating a submission"""
        submission = await Submission.create(
            submission_id="test-sub-123",
            name="Test Skill",
            repo_url="https://github.com/test/skill",
            description="A test skill",
            status=SubmissionStatus.CREATING_ISSUE,
        )

        assert submission.id is not None
        assert submission.submission_id == "test-sub-123"
        assert submission.status == SubmissionStatus.CREATING_ISSUE

    @pytest.mark.asyncio
    async def test_submission_with_issue(self, db):
        """Test submission with issue info"""
        submission = await Submission.create(
            submission_id="test-sub-456",
            name="Test Skill",
            repo_url="https://github.com/test/skill",
            status=SubmissionStatus.ISSUE_CREATED,
            issue_number=123,
            issue_url="https://gitea.example.com/issues/123",
        )

        assert submission.issue_number == 123
        assert submission.issue_url is not None

    @pytest.mark.asyncio
    async def test_submission_with_error(self, db):
        """Test submission with error"""
        submission = await Submission.create(
            submission_id="test-sub-789",
            name="Test Skill",
            repo_url="https://github.com/test/skill",
            status=SubmissionStatus.ISSUE_FAILED,
            error_message="Network error",
        )

        assert submission.status == SubmissionStatus.ISSUE_FAILED
        assert submission.error_message == "Network error"


class TestSubmissionEvent:
    """Test SubmissionEvent model"""

    @pytest.mark.asyncio
    async def test_create_event(self, db):
        """Test creating a submission event"""
        submission = await Submission.create(
            submission_id="event-test-1",
            name="Test",
            repo_url="https://github.com/test/skill",
            status=SubmissionStatus.CREATING_ISSUE,
        )

        event = await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.CREATED,
            new_status=SubmissionStatus.CREATING_ISSUE,
            message="Submission created",
            triggered_by="user",
        )

        assert event.id is not None
        assert event.event_type == SubmissionEventType.CREATED

    @pytest.mark.asyncio
    async def test_event_with_details(self, db):
        """Test event with details"""
        submission = await Submission.create(
            submission_id="event-test-2",
            name="Test",
            repo_url="https://github.com/test/skill",
            status=SubmissionStatus.ISSUE_CREATED,
        )

        event = await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.ISSUE_CREATE_SUCCESS,
            new_status=SubmissionStatus.ISSUE_CREATED,
            message="Issue created successfully",
            details={"issue_number": 123},
            triggered_by="system",
        )

        assert event.details["issue_number"] == 123


class TestSubmissionStatus:
    """Test SubmissionStatus enum"""

    def test_status_values(self):
        """Test status enum values"""
        assert SubmissionStatus.CREATING_ISSUE.value == "creating_issue"
        assert SubmissionStatus.ISSUE_CREATED.value == "issue_created"
        assert SubmissionStatus.ISSUE_FAILED.value == "issue_failed"


class TestSubmissionEventType:
    """Test SubmissionEventType enum"""

    def test_event_type_values(self):
        """Test event type enum values"""
        assert SubmissionEventType.CREATED.value == "created"
        assert SubmissionEventType.ISSUE_CREATE_SUCCESS.value == "issue_create_success"
        assert SubmissionEventType.ISSUE_CREATE_FAILED.value == "issue_create_failed"
