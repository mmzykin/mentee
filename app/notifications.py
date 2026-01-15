"""Notification functions for sending messages to students and mentors."""
from telegram.ext import ContextTypes

import database as db


async def notify_student(
    context: ContextTypes.DEFAULT_TYPE, student_user_id: int, message: str
):
    """Send notification to student."""
    try:
        await context.bot.send_message(chat_id=student_user_id, text=message, parse_mode="HTML")
        return True
    except Exception as e:
        print(f"Failed to notify student {student_user_id}: {e}")
        return False


async def notify_mentors(
    context: ContextTypes.DEFAULT_TYPE,
    student_id: int,
    message: str,
    keyboard=None,
    fallback_to_all=True,
):
    """
    Send notification to student's assigned mentors.
    If no mentors assigned and fallback_to_all=True, notify all admins.
    Returns number of successful notifications.
    """
    mentor_ids = db.get_student_mentor_ids(student_id)

    # Fallback to all admins if no mentors assigned
    if not mentor_ids and fallback_to_all:
        admins = db.get_all_admins()
        mentor_ids = [a["user_id"] for a in admins]

    sent = 0
    for mentor_id in mentor_ids:
        try:
            await context.bot.send_message(
                chat_id=mentor_id, text=message, parse_mode="HTML", reply_markup=keyboard
            )
            sent += 1
        except Exception as e:
            print(f"Failed to notify mentor {mentor_id}: {e}")
    return sent
