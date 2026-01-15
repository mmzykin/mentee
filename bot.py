#!/usr/bin/env python3
# pyright: reportUnusedImport=false
"""
Mentee Bot - Entry Point

This file serves as the main entry point for the bot.
The actual implementation is in the `app` package.

To run: python bot.py

Re-exports are provided for backward compatibility with tests.
"""
from app.main import main

# === Re-exports for backward compatibility ===
from app.utils import (  # noqa: F401
    now_msk, to_msk_str, escape_html, get_raw_text, safe_answer, safe_edit, parse_task_format,
)
from app.config import (  # noqa: F401
    BOT_TOKEN, EXEC_TIMEOUT, ADMIN_USERNAMES, BONUS_POINTS_PER_APPROVAL, MSK,
)
from app.keyboards import (  # noqa: F401
    main_menu_keyboard, admin_menu_keyboard, back_to_menu_keyboard, back_to_admin_keyboard,
)
from app.decorators import require_admin, require_registered  # noqa: F401
from app.code_runner import (  # noqa: F401
    run_python_code_with_tests, run_go_code_with_tests, run_code_with_tests,
)
from app.notifications import notify_student, notify_mentors  # noqa: F401
from app.handlers.common import (  # noqa: F401
    start, help_cmd, register, cancel, topics_cmd, leaderboard_cmd,
)
from app.handlers.menu import (  # noqa: F401
    menu_callback, modules_callback, module_callback, topic_callback,
)
from app.handlers.gamble import dailyspin_callback, gamble_callback  # noqa: F401
from app.handlers.tasks import (  # noqa: F401
    show_task_view, task_callback, opentask_callback, starttimer_callback,
    resettimer_callback, submit_callback,
)
from app.handlers.file_handler import handle_file, process_submission  # noqa: F401
from app.handlers.announcements import announcements_callback  # noqa: F401
from app.handlers.student import (  # noqa: F401
    myattempts_callback, mycode_callback, myassigned_callback,
)
from app.handlers.meetings import (  # noqa: F401
    meetings_callback, meeting_action_callback, meeting_slot_callback,
    meeting_slot_time_callback, meeting_duration_callback, meeting_request_duration_callback,
)
from app.handlers.quiz import quiz_callback, show_quiz_question, show_quiz_results  # noqa: F401
from app.handlers.text_handler import handle_text  # noqa: F401
from app.background import send_meeting_reminders  # noqa: F401
from app.handlers.admin.base import (  # noqa: F401
    admin_callback, create_callback, student_callback, recent_callback, bytask_callback,
    attempts_callback, code_callback, approve_callback, unapprove_callback, admintask_callback,
    cheater_callback, feedback_callback, delsub_callback, assign_callback, assignmod_callback,
    assigntopic_callback, toggleassign_callback, assigned_callback, unassign_callback,
    editname_callback, mentors_callback, addmentor_callback, unmentor_callback, hired_callback,
    archive_callback, skip_feedback_callback, archived_student_callback, restore_callback,
    admin_panel, gen_codes, del_task_cmd, del_module_cmd, del_topic_cmd,
)

if __name__ == "__main__":
    main()
