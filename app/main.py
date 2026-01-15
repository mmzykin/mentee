"""
Main entry point for the bot.

This file handles Application setup and handler registration.
Handlers are imported from modular files in app/handlers/.

Migration status:
✅ config.py - done
✅ utils.py - done
✅ keyboards.py - done
✅ decorators.py - done
✅ code_runner.py - done
✅ notifications.py - done
✅ handlers/common.py - done
✅ handlers/menu.py - done
⏳ handlers/tasks.py - pending
⏳ handlers/student.py - pending
⏳ handlers/gamble.py - pending
⏳ handlers/announcements.py - pending
⏳ handlers/meetings.py - pending
⏳ handlers/quiz.py - pending
⏳ handlers/text_handler.py - pending
⏳ handlers/file_handler.py - pending
⏳ handlers/admin/* - pending
⏳ background.py - pending
"""
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

import database as db
from app.config import BOT_TOKEN

# === MIGRATED HANDLERS ===
from app.handlers.common import (
    start,
    help_cmd,
    register,
    cancel,
    topics_cmd,
    leaderboard_cmd,
)
from app.handlers.menu import (
    menu_callback,
    modules_callback,
    module_callback,
    topic_callback,
)
from app.handlers.gamble import (
    dailyspin_callback,
    gamble_callback,
)
from app.handlers.tasks import (
    task_callback,
    opentask_callback,
    starttimer_callback,
    resettimer_callback,
    submit_callback,
)
from app.handlers.file_handler import handle_file
from app.handlers.announcements import announcements_callback
from app.handlers.student import (
    myattempts_callback,
    mycode_callback,
    myassigned_callback,
)
from app.handlers.meetings import (
    meetings_callback,
    meeting_action_callback,
    meeting_slot_callback,
    meeting_slot_time_callback,
    meeting_duration_callback,
    meeting_request_duration_callback,
)
from app.handlers.quiz import quiz_callback
from app.handlers.text_handler import handle_text
from app.background import send_meeting_reminders
from app.handlers.admin.base import (
    admin_callback,
    create_callback,
    student_callback,
    recent_callback,
    bytask_callback,
    attempts_callback,
    code_callback,
    approve_callback,
    unapprove_callback,
    admintask_callback,
    cheater_callback,
    feedback_callback,
    delsub_callback,
    assign_callback,
    assignmod_callback,
    assigntopic_callback,
    toggleassign_callback,
    assigned_callback,
    unassign_callback,
    editname_callback,
    mentors_callback,
    addmentor_callback,
    unmentor_callback,
    hired_callback,
    archive_callback,
    skip_feedback_callback,
    archived_student_callback,
    restore_callback,
    admin_panel,
    gen_codes,
    del_task_cmd,
    del_module_cmd,
    del_topic_cmd,
)



def main():
    """Initialize and run the bot."""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("Set BOT_TOKEN!")
        sys.exit(1)
    
    db.init_db()
    deleted = db.cleanup_old_code()
    if deleted:
        print(f"Cleaned {deleted} old submissions")
    
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )
    
    # === Command handlers ===
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("topics", topics_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    
    # Admin commands
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("deltask", del_task_cmd))
    app.add_handler(CommandHandler("delmodule", del_module_cmd))
    app.add_handler(CommandHandler("deltopic", del_topic_cmd))
    app.add_handler(CommandHandler("gencodes", gen_codes))
    
    # === Callback handlers - migrated ===
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu:"))
    app.add_handler(CallbackQueryHandler(modules_callback, pattern="^modules:"))
    app.add_handler(CallbackQueryHandler(module_callback, pattern="^module:"))
    app.add_handler(CallbackQueryHandler(topic_callback, pattern="^topic:"))
    
    # === Callback handlers - from legacy ===
    app.add_handler(CallbackQueryHandler(task_callback, pattern="^task:"))
    app.add_handler(CallbackQueryHandler(opentask_callback, pattern="^opentask:"))
    app.add_handler(CallbackQueryHandler(starttimer_callback, pattern="^starttimer:"))
    app.add_handler(CallbackQueryHandler(resettimer_callback, pattern="^resettimer:"))
    app.add_handler(CallbackQueryHandler(dailyspin_callback, pattern="^dailyspin"))
    app.add_handler(CallbackQueryHandler(gamble_callback, pattern="^gamble:"))
    app.add_handler(CallbackQueryHandler(submit_callback, pattern="^submit:"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))
    app.add_handler(CallbackQueryHandler(create_callback, pattern="^create:"))
    app.add_handler(CallbackQueryHandler(student_callback, pattern="^student:"))
    app.add_handler(CallbackQueryHandler(recent_callback, pattern="^recent:"))
    app.add_handler(CallbackQueryHandler(bytask_callback, pattern="^bytask:"))
    app.add_handler(CallbackQueryHandler(attempts_callback, pattern="^attempts:"))
    app.add_handler(CallbackQueryHandler(code_callback, pattern="^code:"))
    app.add_handler(CallbackQueryHandler(approve_callback, pattern="^approve:"))
    app.add_handler(CallbackQueryHandler(unapprove_callback, pattern="^unapprove:"))
    app.add_handler(
        CallbackQueryHandler(admintask_callback, pattern="^admintask:|^deltask:|^deltask_confirm:")
    )
    app.add_handler(CallbackQueryHandler(cheater_callback, pattern="^cheater:"))
    app.add_handler(CallbackQueryHandler(feedback_callback, pattern="^feedback:"))
    app.add_handler(CallbackQueryHandler(delsub_callback, pattern="^delsub:"))
    app.add_handler(CallbackQueryHandler(assign_callback, pattern="^assign:"))
    app.add_handler(CallbackQueryHandler(assignmod_callback, pattern="^assignmod:"))
    app.add_handler(CallbackQueryHandler(assigntopic_callback, pattern="^assigntopic:"))
    app.add_handler(CallbackQueryHandler(toggleassign_callback, pattern="^toggleassign:"))
    app.add_handler(CallbackQueryHandler(assigned_callback, pattern="^assigned:"))
    app.add_handler(CallbackQueryHandler(unassign_callback, pattern="^unassign:"))
    app.add_handler(CallbackQueryHandler(myattempts_callback, pattern="^myattempts:"))
    app.add_handler(CallbackQueryHandler(mycode_callback, pattern="^mycode:"))
    app.add_handler(CallbackQueryHandler(myassigned_callback, pattern="^myassigned:"))
    app.add_handler(CallbackQueryHandler(editname_callback, pattern="^editname:"))
    app.add_handler(CallbackQueryHandler(mentors_callback, pattern="^mentors:"))
    app.add_handler(CallbackQueryHandler(addmentor_callback, pattern="^addmentor:"))
    app.add_handler(CallbackQueryHandler(unmentor_callback, pattern="^unmentor:"))
    app.add_handler(CallbackQueryHandler(hired_callback, pattern="^hired:"))
    app.add_handler(CallbackQueryHandler(archive_callback, pattern="^archive:"))
    app.add_handler(CallbackQueryHandler(skip_feedback_callback, pattern="^skip_feedback:"))
    app.add_handler(CallbackQueryHandler(archived_student_callback, pattern="^archived_student:"))
    app.add_handler(CallbackQueryHandler(restore_callback, pattern="^restore:"))
    app.add_handler(CallbackQueryHandler(announcements_callback, pattern="^announcements:"))
    app.add_handler(CallbackQueryHandler(meetings_callback, pattern="^meetings:"))
    app.add_handler(
        CallbackQueryHandler(
            meeting_action_callback,
            pattern="^meeting_confirm:|^meeting_decline:|^meeting_approve:|^meeting_reject:",
        )
    )
    app.add_handler(CallbackQueryHandler(meeting_slot_callback, pattern="^meeting_slot:"))
    app.add_handler(CallbackQueryHandler(meeting_slot_time_callback, pattern="^meeting_slot_time:"))
    app.add_handler(CallbackQueryHandler(meeting_duration_callback, pattern="^meeting_dur:"))
    app.add_handler(
        CallbackQueryHandler(meeting_request_duration_callback, pattern="^meeting_req_dur:")
    )
    app.add_handler(CallbackQueryHandler(quiz_callback, pattern="^quiz:"))
    
    # === Message handlers ===
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.FileExtension("py"), handle_file))
    
    # === Background jobs ===
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(send_meeting_reminders, interval=300, first=10)
        print("Meeting reminders job scheduled (every 5 min)")
    
    print("Bot starting...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
