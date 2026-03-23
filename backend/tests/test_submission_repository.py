"""
Tests for Submission Repository - 提交仓库测试
"""
import pytest
from datetime import datetime, timedelta

from app.repositories.submission_repository import SubmissionRepository, SubmissionEventRepository
from app.models.submission import Submission, SubmissionEvent, SubmissionStatus, SubmissionEventType


class TestSubmissionRepository:
    """Test submission repository"""

    @pytest.fixture
    async def setup_submissions(self, db):
        """Setup test submissions"""
        sub1 = await Submission.create(
            submission_id="repo-sub-1",
            name="Repo Sub 1",
            repo_url="https://github.com/test/sub1",
            description="Test submission 1",
            status=SubmissionStatus.ISSUE_CREATED,
            issue_number=101,
        )
        sub2 = await Submission.create(
            submission_id="repo-sub-2",
            name="Repo Sub 2",
            repo_url="https://github.com/test/sub2",
            description="Test submission 2",
            status=SubmissionStatus.APPROVED,
            issue_number=102,
        )
        sub3 = await Submission.create(
            submission_id="repo-sub-3",
            name="Repo Sub 3",
            repo_url="https://github.com/test/sub3",
            description="Test submission 3",
            status=SubmissionStatus.ISSUE_FAILED,
        )
        return [sub1, sub2, sub3]

    @pytest.mark.asyncio
    async def test_find_by_submission_id(self, db, setup_submissions):
        """Test finding submission by submission_id"""
        repo = SubmissionRepository()
        submission = await repo.find_by_submission_id("repo-sub-1")

        assert submission is not None
        assert submission.name == "Repo Sub 1"

    @pytest.mark.asyncio
    async def test_find_by_submission_id_not_found(self, db):
        """Test finding non-existent submission_id - 边界值"""
        repo = SubmissionRepository()
        submission = await repo.find_by_submission_id("non-existent")

        assert submission is None

    @pytest.mark.asyncio
    async def test_find_by_issue_number(self, db, setup_submissions):
        """Test finding submission by issue number"""
        repo = SubmissionRepository()
        submission = await repo.find_by_issue_number(101)

        assert submission is not None
        assert submission.submission_id == "repo-sub-1"

    @pytest.mark.asyncio
    async def test_find_by_issue_number_not_found(self, db):
        """Test finding non-existent issue number - 边界值"""
        repo = SubmissionRepository()
        submission = await repo.find_by_issue_number(99999)

        assert submission is None

    @pytest.mark.asyncio
    async def test_find_pending_sync(self, db, setup_submissions):
        """Test finding pending sync submissions"""
        repo = SubmissionRepository()
        submissions = await repo.find_pending_sync()

        # Should include ISSUE_CREATED and APPROVED with issue_number
        assert len(submissions) >= 2

    @pytest.mark.asyncio
    async def test_find_by_status(self, db, setup_submissions):
        """Test finding submissions by status"""
        repo = SubmissionRepository()
        submissions = await repo.find_by_status(SubmissionStatus.ISSUE_CREATED)

        assert len(submissions) >= 1
        for sub in submissions:
            assert sub.status == SubmissionStatus.ISSUE_CREATED

    @pytest.mark.asyncio
    async def test_find_by_status_pagination(self, db, setup_submissions):
        """Test finding by status with pagination - 边界值"""
        repo = SubmissionRepository()
        submissions = await repo.find_by_status(
            SubmissionStatus.ISSUE_CREATED,
            skip=0,
            limit=1
        )

        assert len(submissions) <= 1

    @pytest.mark.asyncio
    async def test_count_by_status(self, db, setup_submissions):
        """Test counting by status"""
        repo = SubmissionRepository()
        count = await repo.count_by_status(SubmissionStatus.ISSUE_CREATED)

        assert count >= 1

    @pytest.mark.asyncio
    async def test_update_status(self, db, setup_submissions):
        """Test updating submission status"""
        repo = SubmissionRepository()
        submission = setup_submissions[0]

        await repo.update_status(
            submission,
            SubmissionStatus.APPROVED,
            approved_by=1,
            approved_by_employee_id="ADMIN001"
        )

        await submission.refresh_from_db()
        assert submission.status == SubmissionStatus.APPROVED
        assert submission.approved_by == 1


class TestSubmissionEventRepository:
    """Test submission event repository"""

    @pytest.fixture
    async def setup_events(self, db):
        """Setup test events"""
        submission = await Submission.create(
            submission_id="event-test-sub",
            name="Event Test",
            repo_url="https://github.com/test/events",
            status=SubmissionStatus.ISSUE_CREATED,
        )

        event1 = await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.CREATED,
            new_status=SubmissionStatus.CREATING_ISSUE,
            message="Submission created",
            triggered_by="user"
        )
        event2 = await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.ISSUE_CREATE_SUCCESS,
            old_status=SubmissionStatus.CREATING_ISSUE,
            new_status=SubmissionStatus.ISSUE_CREATED,
            message="Issue created",
            triggered_by="system"
        )

        return {"submission": submission, "events": [event1, event2]}

    @pytest.mark.asyncio
    async def test_find_by_submission(self, db, setup_events):
        """Test finding events by submission"""
        repo = SubmissionEventRepository()
        events = await repo.find_by_submission(setup_events["submission"])

        assert len(events) >= 2

    @pytest.mark.asyncio
    async def test_find_by_submission_pagination(self, db, setup_events):
        """Test finding events with pagination - 边界值"""
        repo = SubmissionEventRepository()
        events = await repo.find_by_submission(
            setup_events["submission"],
            skip=0,
            limit=1
        )

        assert len(events) <= 1

    @pytest.mark.asyncio
    async def test_find_by_submission_empty(self, db):
        """Test finding events for submission with no events - 边界值"""
        submission = await Submission.create(
            submission_id="no-events-sub",
            name="No Events",
            repo_url="https://github.com/test/noevents",
            status=SubmissionStatus.ISSUE_CREATED,
        )

        repo = SubmissionEventRepository()
        events = await repo.find_by_submission(submission)

        assert len(events) == 0
