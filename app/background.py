"""Background tasks."""
from telegram.ext import ContextTypes

import database as db
from app.utils import escape_html, to_msk_str


async def send_meeting_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Background job to send meeting reminders."""
    reminders = db.get_pending_reminders()

    for meeting in reminders:
        reminder_type = meeting["reminder_type"]
        time_text = "24 часа" if reminder_type == "24h" else "1 час"
        emoji = "⏰" if reminder_type == "1h" else "📅"

        dt = to_msk_str(meeting["scheduled_at"])

        message = (
            f"{emoji} <b>Напоминание о встрече!</b>\n\n"
            f"<b>{escape_html(meeting['title'])}</b>\n"
            f"🕐 {dt} (через {time_text})\n"
            f"⏱ {meeting['duration_minutes']} мин\n\n"
            f"🔗 <a href='{meeting['meeting_link']}'>Открыть Телемост</a>"
        )

        # Send to student
        if meeting["student_id"]:
            student = db.get_student_by_id(meeting["student_id"])
            if student:
                try:
                    await context.bot.send_message(
                        student["user_id"],
                        message,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    print(f"Failed to send reminder to student {student['user_id']}: {e}")

        # Send to admin/mentor who created it
        try:
            await context.bot.send_message(
                meeting["created_by"],
                f"👤 <b>Напоминание (для ментора)</b>\n\n" + message,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            print(f"Failed to send reminder to admin {meeting['created_by']}: {e}")

        # Mark reminder as sent
        db.mark_reminder_sent(meeting["id"], reminder_type)
