"""Announcements handlers."""
from telegram import Update
from telegram.ext import ContextTypes

import database as db
from app.utils import escape_html, safe_answer, to_msk_str
from app.keyboards import back_to_menu_keyboard


async def announcements_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle announcements:list callback."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    student = db.get_student(user.id)

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "list"

    if action == "list":
        announcements = db.get_announcements(10)
        text = "📢 <b>Объявления</b>\n\n"
        if announcements:
            for a in announcements:
                date = to_msk_str(a["created_at"], date_only=True)
                text += f"• [{date}] <b>{escape_html(a['title'])}</b>\n"
                if len(a["content"]) > 100:
                    text += f"  {escape_html(a['content'][:100])}...\n"
                else:
                    text += f"  {escape_html(a['content'])}\n"
                text += "\n"
                # Mark as read
                if student:
                    db.mark_announcement_read(a["id"], student["id"])
        else:
            text += "<i>Пока нет объявлений</i>\n"

        await query.edit_message_text(
            text, reply_markup=back_to_menu_keyboard(), parse_mode="HTML"
        )
