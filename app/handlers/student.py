"""Student personal handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from app.utils import escape_html, safe_answer, to_msk_str
from app.keyboards import back_to_menu_keyboard


async def myattempts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Student's own attempts."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    student = db.get_student(user.id)
    if not student:
        await query.edit_message_text("Не зарегистрирован.", reply_markup=back_to_menu_keyboard())
        return

    parts = query.data.split(":")
    page = int(parts[1]) if len(parts) > 1 else 0
    per_page = 10

    subs = db.get_student_submissions(student["id"])
    total = len(subs)
    start = page * per_page
    end = start + per_page
    page_subs = subs[start:end]

    if not subs:
        text = "📋 <b>Мои попытки</b>\n\n<i>Пока нет попыток</i>"
        keyboard = [[InlineKeyboardButton("« Назад", callback_data="menu:mystats")]]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )
        return

    text = f"📋 <b>Мои попытки</b> ({total} всего)\n\n"
    keyboard = []
    for sub in page_subs:
        status = "✅" if sub["passed"] else "❌"
        approved = "⭐" if sub.get("approved") else ""
        feedback = "💬" if sub.get("feedback") else ""
        date = to_msk_str(sub["submitted_at"])
        task = db.get_task(sub["task_id"])
        task_title = task["title"][:20] if task else sub["task_id"]
        btn = f"{status}{approved}{feedback} {task_title} {date}"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"mycode:{sub['id']}")])

    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"myattempts:{page-1}"))
    if end < total:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"myattempts:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("« Назад", callback_data="menu:mystats")])
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def mycode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Student views their own submission."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    student = db.get_student(user.id)
    if not student:
        await query.edit_message_text("Не зарегистрирован.", reply_markup=back_to_menu_keyboard())
        return

    sub_id = int(query.data.split(":")[1])
    sub = db.get_submission_by_id(sub_id)

    if not sub or sub["student_id"] != student["id"]:
        await query.edit_message_text("Не найдено.", reply_markup=back_to_menu_keyboard())
        return

    status = "✅ Решено" if sub["passed"] else "❌ Не пройдено"
    approved = " ⭐Аппрувнуто" if sub.get("approved") else ""
    task = db.get_task(sub["task_id"])
    task_title = escape_html(task["title"]) if task else sub["task_id"]

    code = sub["code"] or "[удалён]"
    if len(code) > 2000:
        code = code[:2000] + "\n...(обрезано)"

    text = (
        f"<b>{status}{approved}</b>\n"
        f"Задание: <b>{task_title}</b>\n"
        f"Время: {to_msk_str(sub['submitted_at'])}\n\n"
        f"<pre>{escape_html(code)}</pre>"
    )

    if sub.get("feedback"):
        text += f"\n\n💬 <b>Фидбек от ментора:</b>\n{escape_html(sub['feedback'])}"

    keyboard = [[InlineKeyboardButton("« Мои попытки", callback_data="myattempts:0")]]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def myassigned_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Student's assigned tasks."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    student = db.get_student(user.id)
    if not student:
        await query.edit_message_text("Не зарегистрирован.", reply_markup=back_to_menu_keyboard())
        return

    assigned = db.get_assigned_tasks(student["id"])

    if not assigned:
        text = (
            "📌 <b>Назначенные мне задания</b>\n\n"
            "<i>Пока ничего не назначено</i>"
        )
        keyboard = [[InlineKeyboardButton("« Главное меню", callback_data="menu:main")]]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )
        return

    text = f"📌 <b>Назначенные мне задания</b> ({len(assigned)})\n\n"
    keyboard = []
    for t in assigned:
        solved = db.has_solved(student["id"], t["task_id"])
        status = "✅" if solved else "⬜"
        btn = f"{status} {t['title']}"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"task:{t['task_id']}")])

    keyboard.append([InlineKeyboardButton("« Главное меню", callback_data="menu:main")])
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )
