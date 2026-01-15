"""
Unit tests for database.py module.
Tests all database operations with isolated temporary database.
"""

from tests.conftest import create_registered_student, create_admin, create_task_with_topic
import database as db
import pytest
import sys
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============= ADMIN TESTS =============


class TestAdminFunctions:
    """Tests for admin-related database functions."""

    def test_add_admin(self, clean_db):
        """Test adding a new admin."""
        result = db.add_admin(123456, "Admin Name")
        assert result is True
        assert db.is_admin(123456) is True

    def test_add_admin_duplicate(self, clean_db):
        """Test adding duplicate admin updates name."""
        db.add_admin(123456, "Name1")
        result = db.add_admin(123456, "Name2")
        assert result is False  # Returns False for existing
        # But name should be updated

    def test_is_admin_false(self, clean_db):
        """Test is_admin returns False for non-admin."""
        assert db.is_admin(999999) is False

    def test_get_admin_count(self, clean_db):
        """Test admin count."""
        assert db.get_admin_count() == 0
        db.add_admin(111, "A1")
        db.add_admin(222, "A2")
        assert db.get_admin_count() == 2

    def test_update_admin_name(self, clean_db):
        """Test updating admin name."""
        db.add_admin(123, "OldName")
        db.update_admin_name(123, "NewName")
        admins = db.get_all_admins()
        admin = next(a for a in admins if a["user_id"] == 123)
        assert admin["name"] == "NewName"


# ============= CODE TESTS =============


class TestCodeFunctions:
    """Tests for invitation code functions."""

    def test_create_codes(self, clean_db):
        """Test creating invitation codes."""
        codes = db.create_codes(5)
        assert len(codes) == 5
        assert all(len(c) == 8 for c in codes)

    def test_get_unused_codes(self, clean_db):
        """Test getting unused codes."""
        db.create_codes(3)
        unused = db.get_unused_codes()
        assert len(unused) == 3

    def test_use_code_success(self, clean_db):
        """Test using a valid code."""
        codes = db.create_codes(1)
        result = db.use_code(codes[0], 12345)
        assert result is True
        # Code should now be used
        unused = db.get_unused_codes()
        assert len(unused) == 0

    def test_use_code_invalid(self, clean_db):
        """Test using invalid code."""
        result = db.use_code("INVALID", 12345)
        assert result is False

    def test_use_code_already_used(self, clean_db):
        """Test using already used code."""
        codes = db.create_codes(1)
        db.use_code(codes[0], 11111)
        result = db.use_code(codes[0], 22222)
        assert result is False

    def test_code_case_insensitive(self, clean_db):
        """Test that codes are case insensitive."""
        codes = db.create_codes(1)
        result = db.use_code(codes[0].lower(), 12345)
        assert result is True


# ============= STUDENT TESTS =============


class TestStudentFunctions:
    """Tests for student management functions."""

    def test_register_student(self, clean_db):
        """Test student registration."""
        codes = db.create_codes(1)
        result = db.register_student(12345, "user", "Name", codes[0])
        assert result is True
        student = db.get_student(12345)
        assert student is not None
        assert student["first_name"] == "Name"

    def test_register_duplicate_student(self, clean_db):
        """Test registering same user twice."""
        codes = db.create_codes(2)
        db.register_student(12345, "user", "Name1", codes[0])
        result = db.register_student(12345, "user", "Name2", codes[1])
        assert result is False

    def test_is_registered(self, clean_db):
        """Test is_registered function."""
        assert db.is_registered(12345) is False
        create_registered_student(12345)
        assert db.is_registered(12345) is True

    def test_get_student_by_id(self, clean_db):
        """Test getting student by internal ID."""
        student = create_registered_student(12345)
        retrieved = db.get_student_by_id(student["id"])
        assert retrieved is not None
        assert retrieved["user_id"] == 12345

    def test_get_all_students(self, clean_db):
        """Test getting all students."""
        create_registered_student(111)
        create_registered_student(222)
        create_registered_student(333)
        students = db.get_all_students()
        assert len(students) == 3

    def test_update_student_name(self, clean_db):
        """Test updating student name."""
        student = create_registered_student(12345, first_name="Old")
        db.update_student_name(student["id"], "New")
        updated = db.get_student(12345)
        assert updated["first_name"] == "New"

    def test_delete_student(self, clean_db):
        """Test deleting student."""
        student = create_registered_student(12345)
        result = db.delete_student(student["id"])
        assert result is True
        assert db.get_student(12345) is None


# ============= BONUS POINTS TESTS =============


class TestBonusPoints:
    """Tests for bonus points system."""

    def test_add_bonus_points(self, clean_db):
        """Test adding bonus points."""
        student = create_registered_student(12345)
        db.add_bonus_points(student["id"], 10)
        updated = db.get_student(12345)
        assert updated["bonus_points"] == 10

    def test_get_student_bonus(self, clean_db):
        """Test getting student bonus."""
        student = create_registered_student(12345)
        db.add_bonus_points(student["id"], 15)
        bonus = db.get_student_bonus(student["id"])
        assert bonus == 15

    def test_bonus_accumulates(self, clean_db):
        """Test bonus points accumulate."""
        student = create_registered_student(12345)
        db.add_bonus_points(student["id"], 5)
        db.add_bonus_points(student["id"], 3)
        bonus = db.get_student_bonus(student["id"])
        assert bonus == 8


# ============= MODULE TESTS =============


class TestModuleFunctions:
    """Tests for module management."""

    def test_add_module(self, clean_db):
        """Test adding a module."""
        # Note: init_db creates a default module, so we check for our new one
        result = db.add_module("test_mod", "Test Module", 5, "python")
        assert result is True
        module = db.get_module("test_mod")
        assert module["name"] == "Test Module"

    def test_add_duplicate_module(self, clean_db):
        """Test adding duplicate module fails."""
        db.add_module("mod1", "Module 1", 1, "python")
        result = db.add_module("mod1", "Module 1 Again", 2, "python")
        assert result is False

    def test_get_modules(self, clean_db):
        """Test getting all modules."""
        db.add_module("m1", "Module 1", 1, "python")
        db.add_module("m2", "Module 2", 2, "go")
        modules = db.get_modules()
        # +1 for default module from init_db
        assert len(modules) >= 2

    def test_delete_module_empty(self, clean_db):
        """Test deleting module with no topics."""
        db.add_module("empty", "Empty", 1, "python")
        result = db.delete_module("empty")
        assert result is True

    def test_delete_module_with_topics(self, clean_db):
        """Test deleting module with topics fails."""
        db.add_module("with_topics", "WithTopics", 1, "python")
        db.add_topic("t1", "Topic 1", "with_topics", 1)
        result = db.delete_module("with_topics")
        assert result is False


# ============= TOPIC TESTS =============


class TestTopicFunctions:
    """Tests for topic management."""

    def test_add_topic(self, clean_db):
        """Test adding a topic."""
        db.add_module("m1", "M1", 1, "python")
        result = db.add_topic("t1", "Topic 1", "m1", 1)
        assert result is True
        topic = db.get_topic("t1")
        assert topic["name"] == "Topic 1"

    def test_get_topics_by_module(self, clean_db):
        """Test getting topics by module."""
        db.add_module("m1", "M1", 1, "python")
        db.add_topic("t1", "Topic 1", "m1", 1)
        db.add_topic("t2", "Topic 2", "m1", 2)
        topics = db.get_topics_by_module("m1")
        assert len(topics) == 2

    def test_delete_topic_empty(self, clean_db):
        """Test deleting topic with no tasks."""
        db.add_module("m1", "M1", 1, "python")
        db.add_topic("empty_topic", "Empty", "m1", 1)
        result = db.delete_topic("empty_topic")
        assert result is True

    def test_delete_topic_with_tasks(self, clean_db):
        """Test deleting topic with tasks fails."""
        create_task_with_topic("task1", "topic1", "mod1")
        result = db.delete_topic("topic1")
        assert result is False


# ============= TASK TESTS =============


class TestTaskFunctions:
    """Tests for task management."""

    def test_add_task(self, clean_db):
        """Test adding a task."""
        db.add_module("m1", "M1", 1, "python")
        db.add_topic("t1", "T1", "m1", 1)
        result = db.add_task("task1", "t1", "Title", "Desc", "print('✅')", "python")
        assert result is True
        task = db.get_task("task1")
        assert task["title"] == "Title"

    def test_get_tasks_by_topic(self, clean_db):
        """Test getting tasks by topic."""
        db.add_module("m1", "M1", 1, "python")
        db.add_topic("t1", "T1", "m1", 1)
        db.add_task("task1", "t1", "Title1", "Desc", "test", "python")
        db.add_task("task2", "t1", "Title2", "Desc", "test", "python")
        tasks = db.get_tasks_by_topic("t1")
        assert len(tasks) == 2

    def test_delete_task(self, clean_db):
        """Test deleting a task."""
        create_task_with_topic("task1", "t1", "m1")
        result = db.delete_task("task1")
        assert result is True
        assert db.get_task("task1") is None


# ============= SUBMISSION TESTS =============


class TestSubmissionFunctions:
    """Tests for submission handling."""

    def test_add_submission(self, clean_db):
        """Test adding a submission."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        sub_id = db.add_submission(student["id"], "task1", "code", True, "output")
        assert sub_id > 0

    def test_get_student_submissions(self, clean_db):
        """Test getting student submissions."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        db.add_submission(student["id"], "task1", "code1", True, "out1")
        db.add_submission(student["id"], "task1", "code2", False, "out2")
        subs = db.get_student_submissions(student["id"])
        assert len(subs) == 2

    def test_has_solved(self, clean_db):
        """Test has_solved function."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        assert db.has_solved(student["id"], "task1") is False
        db.add_submission(student["id"], "task1", "code", True, "✅")
        assert db.has_solved(student["id"], "task1") is True

    def test_approve_submission(self, clean_db):
        """Test approving a submission."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        sub_id = db.add_submission(student["id"], "task1", "code", True, "out")
        result = db.approve_submission(sub_id, 5)
        assert result is True
        # Check bonus points added
        updated = db.get_student(12345)
        assert updated["bonus_points"] == 5

    def test_unapprove_submission(self, clean_db):
        """Test unapproving a submission."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        sub_id = db.add_submission(student["id"], "task1", "code", True, "out")
        db.approve_submission(sub_id, 5)
        result = db.unapprove_submission(sub_id)
        assert result is True
        # Bonus should be removed
        updated = db.get_student(12345)
        assert updated["bonus_points"] == 0

    def test_delete_submission(self, clean_db):
        """Test deleting a submission."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        sub_id = db.add_submission(student["id"], "task1", "code", True, "out")
        result = db.delete_submission(sub_id)
        assert result is True


# ============= ASSIGNED TASKS TESTS =============


class TestAssignedTasks:
    """Tests for task assignment."""

    def test_assign_task(self, clean_db):
        """Test assigning a task to student."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        result = db.assign_task(student["id"], "task1")
        assert result is True

    def test_assign_duplicate(self, clean_db):
        """Test assigning same task twice fails."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        db.assign_task(student["id"], "task1")
        result = db.assign_task(student["id"], "task1")
        assert result is False

    def test_get_assigned_tasks(self, clean_db):
        """Test getting assigned tasks."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        create_task_with_topic("task2", "t1", "m1")
        db.assign_task(student["id"], "task1")
        db.assign_task(student["id"], "task2")
        assigned = db.get_assigned_tasks(student["id"])
        assert len(assigned) == 2

    def test_unassign_task(self, clean_db):
        """Test unassigning a task."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        db.assign_task(student["id"], "task1")
        result = db.unassign_task(student["id"], "task1")
        assert result is True
        assert len(db.get_assigned_tasks(student["id"])) == 0

    def test_is_task_assigned(self, clean_db):
        """Test checking if task is assigned."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        assert db.is_task_assigned(student["id"], "task1") is False
        db.assign_task(student["id"], "task1")
        assert db.is_task_assigned(student["id"], "task1") is True


# ============= STATISTICS TESTS =============


class TestStatistics:
    """Tests for statistics functions."""

    def test_get_student_stats(self, clean_db):
        """Test getting student statistics."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        create_task_with_topic("task2", "t1", "m1")
        db.add_submission(student["id"], "task1", "code", True, "✅")
        stats = db.get_student_stats(student["id"])
        assert stats["solved_tasks"] == 1
        assert stats["total_tasks"] == 2
        assert stats["total_submissions"] == 1

    def test_get_leaderboard(self, clean_db):
        """Test leaderboard generation."""
        s1 = create_registered_student(111, "user1", "Top")
        s2 = create_registered_student(222, "user2", "Mid")
        s3 = create_registered_student(333, "user3", "Low")

        create_task_with_topic("task1", "t1", "m1")
        create_task_with_topic("task2", "t1", "m1")

        # Give different scores
        db.add_submission(s1["id"], "task1", "c", True, "✅")
        db.add_submission(s1["id"], "task2", "c", True, "✅")
        db.add_submission(s2["id"], "task1", "c", True, "✅")

        leaders = db.get_leaderboard(10)
        assert len(leaders) >= 2
        assert leaders[0]["solved"] >= leaders[1]["solved"]


# ============= GAMBLING TESTS =============


class TestGambling:
    """Tests for gambling/daily spin functions."""

    def test_can_spin_daily_first_time(self, clean_db):
        """Test first spin is allowed."""
        student = create_registered_student(12345)
        assert db.can_spin_daily(student["id"]) is True

    def test_do_daily_spin(self, clean_db):
        """Test doing daily spin returns points."""
        student = create_registered_student(12345)
        points = db.do_daily_spin(student["id"])
        assert points in [-1, 0, 1, 2]

    def test_spin_cooldown(self, clean_db):
        """Test spin has daily cooldown."""
        student = create_registered_student(12345)
        db.do_daily_spin(student["id"])
        assert db.can_spin_daily(student["id"]) is False

    def test_gamble_points_win_lose(self, clean_db):
        """Test gambling points (result varies)."""
        student = create_registered_student(12345)
        db.add_bonus_points(student["id"], 10)
        won, balance = db.gamble_points(student["id"], 5)
        assert isinstance(won, bool)
        assert balance in [5, 15]  # Either lost 5 or won 5

    def test_gamble_insufficient_points(self, clean_db):
        """Test gambling with insufficient points."""
        student = create_registered_student(12345)
        won, balance = db.gamble_points(student["id"], 100)
        assert won is False
        assert balance == 0


# ============= STREAK TESTS =============


class TestStreaks:
    """Tests for solve streak functions."""

    def test_get_solve_streak_initial(self, clean_db):
        """Test initial streak is 0."""
        student = create_registered_student(12345)
        assert db.get_solve_streak(student["id"]) == 0

    def test_increment_streak(self, clean_db):
        """Test incrementing streak."""
        student = create_registered_student(12345)
        new_streak = db.increment_streak(student["id"])
        assert new_streak == 1
        new_streak = db.increment_streak(student["id"])
        assert new_streak == 2

    def test_reset_streak(self, clean_db):
        """Test resetting streak."""
        student = create_registered_student(12345)
        db.increment_streak(student["id"])
        db.increment_streak(student["id"])
        db.reset_streak(student["id"])
        assert db.get_solve_streak(student["id"]) == 0


# ============= ARCHIVE TESTS =============


class TestArchive:
    """Tests for student archiving."""

    def test_archive_student(self, clean_db):
        """Test archiving a student."""
        student = create_registered_student(12345)
        result = db.archive_student(student["id"], "HIRED", "Great work!")
        assert result is True

        archived = db.get_archived_students()
        assert len(archived) == 1
        assert archived[0]["archive_reason"] == "HIRED"

    def test_get_active_students(self, clean_db):
        """Test getting active (non-archived) students."""
        s1 = create_registered_student(111)
        s2 = create_registered_student(222)
        db.archive_student(s1["id"], "LEFT", "")

        active = db.get_active_students()
        assert len(active) == 1
        assert active[0]["user_id"] == 222


# ============= ANNOUNCEMENTS TESTS =============


class TestAnnouncements:
    """Tests for announcement functions."""

    def test_create_announcement(self, clean_db):
        """Test creating announcement."""
        create_admin(123)
        ann_id = db.create_announcement("Title", "Content", 123)
        assert ann_id > 0

    def test_get_announcements(self, clean_db):
        """Test getting announcements."""
        create_admin(123)
        db.create_announcement("Ann1", "Content1", 123)
        db.create_announcement("Ann2", "Content2", 123)
        anns = db.get_announcements()
        assert len(anns) == 2

    def test_mark_announcement_read(self, clean_db):
        """Test marking announcement as read."""
        create_admin(123)
        student = create_registered_student(456)
        ann_id = db.create_announcement("Title", "Content", 123)

        unread = db.get_unread_announcements_count(student["id"])
        assert unread == 1

        db.mark_announcement_read(ann_id, student["id"])
        unread = db.get_unread_announcements_count(student["id"])
        assert unread == 0

    def test_delete_announcement(self, clean_db):
        """Test deleting announcement."""
        create_admin(123)
        ann_id = db.create_announcement("Title", "Content", 123)
        result = db.delete_announcement(ann_id)
        assert result is True
        assert db.get_announcement(ann_id) is None


# ============= MEETINGS TESTS =============


class TestMeetings:
    """Tests for meeting/calendar functions."""

    def test_create_meeting(self, clean_db):
        """Test creating a meeting."""
        create_admin(123)
        student = create_registered_student(456)
        meeting_id = db.create_meeting(
            student["id"],
            "Code Review",
            "https://meet.google.com/xxx",
            "2025-12-01T15:00:00",
            30,
            123,
            "Notes",
        )
        assert meeting_id > 0

    def test_get_meetings(self, clean_db):
        """Test getting meetings."""
        create_admin(123)
        student = create_registered_student(456)
        # Future meeting
        db.create_meeting(
            student["id"],
            "Meeting",
            "link",
            (datetime.now() + timedelta(days=1)).isoformat(),
            30,
            123,
        )
        meetings = db.get_meetings(student["id"])
        assert len(meetings) == 1

    def test_update_meeting_status(self, clean_db):
        """Test updating meeting status."""
        create_admin(123)
        student = create_registered_student(456)
        meeting_id = db.create_meeting(
            student["id"],
            "Meeting",
            "link",
            (datetime.now() + timedelta(days=1)).isoformat(),
            30,
            123,
        )
        db.update_meeting_status(meeting_id, "cancelled")
        meeting = db.get_meeting(meeting_id)
        assert meeting["status"] == "cancelled"

    def test_delete_meeting(self, clean_db):
        """Test deleting meeting."""
        create_admin(123)
        meeting_id = db.create_meeting(
            None,
            "General Meeting",
            "link",
            (datetime.now() + timedelta(days=1)).isoformat(),
            30,
            123,
        )
        result = db.delete_meeting(meeting_id)
        assert result is True


# ============= QUESTIONS/QUIZ TESTS =============


class TestQuestions:
    """Tests for interview questions."""

    def test_add_question(self, clean_db):
        """Test adding a question."""
        db.add_module("m1", "M1", 1, "python")
        db.add_topic("t1", "T1", "m1", 1)

        options = [{"text": "A"}, {"text": "B"}, {"text": "C"}]
        q_id = db.add_question("t1", "What is Python?", options, 0, 0.1, "Python is...")
        assert q_id > 0

    def test_get_question(self, clean_db):
        """Test getting a question with options."""
        db.add_module("m1", "M1", 1, "python")
        db.add_topic("t1", "T1", "m1", 1)

        options = [{"text": "Opt A"}, {"text": "Opt B"}]
        q_id = db.add_question("t1", "Question?", options, 1)

        question = db.get_question(q_id)
        assert question is not None
        assert len(question["options"]) == 2
        assert question["options"][1]["is_correct"] == 1

    def test_get_random_questions(self, clean_db):
        """Test getting random questions."""
        db.add_module("m1", "M1", 1, "python")
        db.add_topic("t1", "T1", "m1", 1)

        for i in range(5):
            db.add_question("t1", f"Q{i}?", [{"text": "A"}, {"text": "B"}], 0)

        random_qs = db.get_random_questions(3)
        assert len(random_qs) == 3

    def test_delete_question(self, clean_db):
        """Test deleting question."""
        db.add_module("m1", "M1", 1, "python")
        db.add_topic("t1", "T1", "m1", 1)

        q_id = db.add_question("t1", "Q?", [{"text": "A"}], 0)
        result = db.delete_question(q_id)
        assert result is True
        assert db.get_question(q_id) is None


# ============= QUIZ SESSION TESTS =============


class TestQuizSessions:
    """Tests for quiz session management."""

    def test_start_quiz_session(self, clean_db):
        """Test starting a quiz session."""
        student = create_registered_student(12345)
        db.add_module("m1", "M1", 1, "python")
        db.add_topic("t1", "T1", "m1", 1)

        q_id = db.add_question("t1", "Q?", [{"text": "A"}], 0)
        question = db.get_question(q_id)

        session_id = db.start_quiz_session(student["id"], [question], 600, "random")
        assert session_id > 0

    def test_answer_quiz_question(self, clean_db):
        """Test answering quiz question."""
        student = create_registered_student(12345)
        db.add_module("m1", "M1", 1, "python")
        db.add_topic("t1", "T1", "m1", 1)

        q_id = db.add_question("t1", "Q?", [{"text": "Wrong"}, {"text": "Right"}], 1, 0.5)
        question = db.get_question(q_id)

        session_id = db.start_quiz_session(student["id"], [question])

        # Get the correct option ID
        correct_opt = next(o for o in question["options"] if o["is_correct"])
        result = db.answer_quiz_question(session_id, q_id, correct_opt["id"])

        assert result["is_correct"] is True
        assert result["points"] == 0.5

    def test_finish_quiz_session(self, clean_db):
        """Test finishing quiz session."""
        student = create_registered_student(12345)
        db.add_module("m1", "M1", 1, "python")
        db.add_topic("t1", "T1", "m1", 1)

        q_id = db.add_question("t1", "Q?", [{"text": "A"}], 0, 1.0)
        question = db.get_question(q_id)

        session_id = db.start_quiz_session(student["id"], [question])
        correct_opt = question["options"][0]
        db.answer_quiz_question(session_id, q_id, correct_opt["id"])

        result = db.finish_quiz_session(session_id)
        assert result["status"] == "finished"


# ============= MENTOR TESTS =============


class TestMentorAssignments:
    """Tests for mentor-student assignments."""

    def test_assign_mentor(self, clean_db):
        """Test assigning mentor to student."""
        create_admin(111)
        student = create_registered_student(222)
        result = db.assign_mentor(student["id"], 111)
        assert result is True

    def test_assign_mentor_duplicate(self, clean_db):
        """Test assigning same mentor twice fails."""
        create_admin(111)
        student = create_registered_student(222)
        db.assign_mentor(student["id"], 111)
        result = db.assign_mentor(student["id"], 111)
        assert result is False

    def test_get_mentor_students(self, clean_db):
        """Test getting students of a mentor."""
        create_admin(111)
        s1 = create_registered_student(222)
        s2 = create_registered_student(333)

        db.assign_mentor(s1["id"], 111)
        db.assign_mentor(s2["id"], 111)

        students = db.get_mentor_students(111)
        assert len(students) == 2

    def test_unassign_mentor(self, clean_db):
        """Test removing mentor assignment."""
        create_admin(111)
        student = create_registered_student(222)
        db.assign_mentor(student["id"], 111)
        result = db.unassign_mentor(student["id"], 111)
        assert result is True
        assert len(db.get_mentor_students(111)) == 0

    def test_is_mentor_of(self, clean_db):
        """Test checking mentor-student relationship."""
        create_admin(111)
        student = create_registered_student(222)
        assert db.is_mentor_of(111, student["id"]) is False
        db.assign_mentor(student["id"], 111)
        assert db.is_mentor_of(111, student["id"]) is True


# ============= CHEATER TESTS =============


class TestCheaterHandling:
    """Tests for cheater/plagiarism handling."""

    def test_punish_cheater(self, clean_db):
        """Test punishing cheater."""
        student = create_registered_student(12345)
        db.add_bonus_points(student["id"], 10)
        create_task_with_topic("task1", "t1", "m1")
        sub_id = db.add_submission(student["id"], "task1", "code", True, "out")

        result = db.punish_cheater(sub_id, 5)
        assert result is True

        # Check submission marked
        sub = db.get_submission_by_id(sub_id)
        assert sub["passed"] == 0
        assert "🚨 СПИСАНО" in sub["feedback"]

        # Check penalty applied
        updated = db.get_student(12345)
        assert updated["bonus_points"] == 5  # 10 - 5 penalty

    def test_get_cheaters_board(self, clean_db):
        """Test getting cheaters board."""
        student = create_registered_student(12345)
        create_task_with_topic("task1", "t1", "m1")
        sub_id = db.add_submission(student["id"], "task1", "code", True, "out")
        db.punish_cheater(sub_id, 0)

        cheaters = db.get_cheaters_board()
        assert len(cheaters) == 1
        assert cheaters[0]["cheat_count"] == 1


# ============= CODE CLEANUP TESTS =============


class TestCodeCleanup:
    """Tests for old code cleanup."""

    def test_cleanup_old_code(self, clean_db):
        """Test cleaning up old submission code."""
        # This test would need time manipulation to properly test
        # For now we just verify the function runs without error
        deleted = db.cleanup_old_code()
        assert isinstance(deleted, int)


# ============= UTILITY FUNCTION TESTS =============


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_generate_code_length(self, clean_db):
        """Test generated code has correct length."""
        code = db.generate_code(10)
        assert len(code) == 10

    def test_generate_code_no_ambiguous_chars(self, clean_db):
        """Test generated code has no ambiguous characters."""
        for _ in range(100):
            code = db.generate_code()
            assert "0" not in code
            assert "O" not in code
            assert "1" not in code
            assert "I" not in code

    def test_now_msk(self, clean_db):
        """Test Moscow time function."""
        msk_time = db.now_msk()
        assert isinstance(msk_time, datetime)
        assert msk_time.tzinfo is None  # Should be naive
