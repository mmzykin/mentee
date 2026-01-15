"""Task viewing and submission handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from app.utils import escape_html, now_msk, safe_answer


async def show_task_view(query, context, task_id: str):
    """Helper to display task view."""
    task = db.get_task(task_id)
    if not task:
        await query.edit_message_text("Не найден.")
        return

    topic = db.get_topic(task["topic_id"])
    back_target = f"topic:{task['topic_id']}" if topic else "modules:list"

    # Check if timer is running for this task
    timer_info = context.user_data.get("task_timer", {})
    timer_active = timer_info.get("task_id") == task_id

    # Check if task was opened in "normal" mode (no timer allowed)
    no_timer_mode = context.user_data.get("no_timer_task") == task_id

    # If neither timer active nor in no_timer mode, show choice screen first
    if not timer_active and not no_timer_mode:
        lang = task.get("language", "python")
        lang_label = "🐹 Go" if lang == "go" else "🐍 Python"
        text = (
            f"📝 <b>{escape_html(task['title'])}</b>\n"
            f"ID: <code>{task_id}</code> • {lang_label}\n\n"
            f"<b>Выбери режим:</b>\n\n"
            f"📖 <b>Обычный</b> — без таймера и бонусов\n\n"
            f"⏱ <b>На время</b> — реши за 10 мин и получи бонус!\n"
            f"Можно сделать ставку для ×2 выигрыша"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📖 Открыть задание", callback_data=f"opentask:{task_id}")],
                [
                    InlineKeyboardButton("⏱ +1⭐", callback_data=f"starttimer:{task_id}:0"),
                    InlineKeyboardButton("🎰 1→2", callback_data=f"starttimer:{task_id}:1"),
                    InlineKeyboardButton("🎰 2→4", callback_data=f"starttimer:{task_id}:2"),
                    InlineKeyboardButton("🎰 3→6", callback_data=f"starttimer:{task_id}:3"),
                ],
                [InlineKeyboardButton("« Назад", callback_data=back_target)],
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        return

    # Show full task
    lang = task.get("language", "python")
    lang_label = "🐹 Go" if lang == "go" else "🐍 Python"
    desc = escape_html(task["description"][:3500])
    text = (
        f"📝 <b>{escape_html(task['title'])}</b>\n"
        f"ID: <code>{task_id}</code> • {lang_label}\n\n"
        f"<pre>{desc}</pre>"
    )

    keyboard_rows = []

    if timer_active:
        elapsed = (now_msk() - timer_info["start_time"]).total_seconds()
        mins, secs = divmod(int(elapsed), 60)
        bet = timer_info.get("bet", 0)
        bet_text = f" (ставка: {bet}⭐)" if bet > 0 else ""
        text += f"\n\n⏱ <b>Таймер: {mins:02d}:{secs:02d}</b>{bet_text}"
        keyboard_rows.append(
            [InlineKeyboardButton("🔄 Сбросить таймер", callback_data=f"resettimer:{task_id}")]
        )

    keyboard_rows.append(
        [InlineKeyboardButton("📤 Отправить решение", callback_data=f"submit:{task_id}")]
    )
    keyboard_rows.append([InlineKeyboardButton("« Назад", callback_data=back_target)])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard_rows), parse_mode="HTML"
    )


async def task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle task:{id} callback."""
    query = update.callback_query
    await safe_answer(query)
    task_id = query.data.split(":")[1]
    await show_task_view(query, context, task_id)


async def opentask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open task in normal mode (no timer allowed)."""
    query = update.callback_query
    await safe_answer(query)
    task_id = query.data.split(":")[1]
    # Mark that this task was opened without timer
    context.user_data["no_timer_task"] = task_id
    # Clear any timer for this task
    context.user_data.pop("task_timer", None)
    # Show the task
    await show_task_view(query, context, task_id)


async def starttimer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start timer for a task with optional bet."""
    query = update.callback_query
    parts = query.data.split(":")
    task_id = parts[1]
    bet = int(parts[2]) if len(parts) > 2 else 0

    # Check if student has enough points for bet
    user = update.effective_user
    student = db.get_student(user.id)
    if bet > 0 and student:
        stats = db.get_student_stats(student["id"])
        if stats["bonus_points"] < bet:
            await safe_answer(
                query,
                f"❌ Недостаточно баллов! У тебя: {stats['bonus_points']}⭐",
                show_alert=True,
            )
            return
        # Deduct bet immediately
        db.add_bonus_points(student["id"], -bet)

    bet_text = f" (ставка {bet}⭐)" if bet > 0 else ""
    await safe_answer(query, f"⏱ Таймер запущен!{bet_text}")

    # Clear no_timer mode if was set
    context.user_data.pop("no_timer_task", None)

    context.user_data["task_timer"] = {"task_id": task_id, "start_time": now_msk(), "bet": bet}
    # Refresh task view to show timer
    await show_task_view(query, context, task_id)


async def resettimer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset timer for a task."""
    query = update.callback_query
    task_id = query.data.split(":")[1]

    # Refund bet if timer had a bet
    timer_info = context.user_data.get("task_timer", {})
    if timer_info.get("task_id") == task_id and timer_info.get("bet", 0) > 0:
        user = update.effective_user
        student = db.get_student(user.id)
        if student:
            db.add_bonus_points(student["id"], timer_info["bet"])
        await safe_answer(
            query, f"⏱ Таймер сброшен! Ставка {timer_info['bet']}⭐ возвращена"
        )
    else:
        await safe_answer(query, "⏱ Таймер сброшен!")

    context.user_data.pop("task_timer", None)
    # Refresh task view
    await show_task_view(query, context, task_id)


async def submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prepare to receive task solution from user."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    if not db.is_registered(user.id) and not db.is_admin(user.id):
        await query.edit_message_text("⛔ /register")
        return
    task_id = query.data.split(":")[1]
    task = db.get_task(task_id)
    if not task:
        await query.edit_message_text("Не найден.")
        return
    context.user_data["pending_task"] = task_id

    # Show timer status if running
    timer_text = ""
    timer_info = context.user_data.get("task_timer", {})
    if timer_info.get("task_id") == task_id:
        elapsed = (now_msk() - timer_info["start_time"]).total_seconds()
        mins, secs = divmod(int(elapsed), 60)
        timer_text = f"\n⏱ Таймер: <b>{mins:02d}:{secs:02d}</b>"
        if elapsed <= 600:
            timer_text += " (успеваешь на +1⭐!)"

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Отмена", callback_data=f"task:{task_id}")]]
    )
    await query.edit_message_text(
        f"📤 <b>{escape_html(task['title'])}</b>{timer_text}\n\nОтправь код:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
