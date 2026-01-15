"""File upload handler."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from app.code_runner import run_code_with_tests
from app.utils import escape_html, now_msk


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle .py file uploads for submissions."""
    task_id = context.user_data.get("pending_task")
    if not task_id:
        return
    if not update.message.document.file_name.endswith(".py"):
        await update.message.reply_text("❌ Нужен .py файл")
        return
    file = await update.message.document.get_file()
    data = await file.download_as_bytearray()
    code = data.decode("utf-8")
    await process_submission(update, context, code)


async def process_submission(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    """Process user submission code for the pending task."""
    task_id = context.user_data.get("pending_task")
    if not task_id:
        return
    user = update.effective_user
    student = db.get_student(user.id)
    is_admin = db.is_admin(user.id)
    if not student and not is_admin:
        await update.message.reply_text("⛔ /register")
        return
    if not student:
        student = {"id": 0}
    if code.startswith("```"):
        lines = code.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines)
    del context.user_data["pending_task"]
    context.user_data.pop("no_timer_task", None)

    # Check timer and bet
    timer_info = context.user_data.get("task_timer", {})
    timer_bonus = False
    timer_text = ""
    bet = 0
    if timer_info.get("task_id") == task_id:
        elapsed = (now_msk() - timer_info["start_time"]).total_seconds()
        mins, secs = divmod(int(elapsed), 60)
        timer_text = f"\n⏱ Время: {mins:02d}:{secs:02d}"
        bet = timer_info.get("bet", 0)
        if elapsed <= 600:  # 10 minutes
            timer_bonus = True
        # Clear timer after submission
        context.user_data.pop("task_timer", None)

    task = db.get_task(task_id)
    if not task:
        await update.message.reply_text("❌ Задание не найдено.")
        return
    lang = task.get("language", "python")
    lang_emoji = "🐹" if lang == "go" else "🐍"
    checking = await update.message.reply_text(f"⏳ Проверяю {lang_emoji}...")
    passed, output = run_code_with_tests(code, task["test_code"], lang)
    sub_id = 0
    if student["id"] != 0:
        sub_id = db.add_submission(student["id"], task_id, code, passed, output)
    safe_output = escape_html(output[:1500])

    if passed:
        bonus_text = ""
        chest_text = ""

        if student["id"] != 0:
            # Award timer bonus if passed within 10 minutes
            if timer_bonus:
                base_bonus = 1 + (bet * 2)  # 1 + double the bet
                db.add_bonus_points(student["id"], base_bonus)
                if bet > 0:
                    bonus_text = (
                        f"\n🎰 <b>+{base_bonus}⭐ выигрыш!</b> (ставка {bet}→{base_bonus})"
                    )
                else:
                    bonus_text = "\n🏃 <b>+1⭐ бонус за скорость!</b>"
            elif bet > 0:
                # Lost bet - time exceeded (bet was already deducted)
                bonus_text = f"\n😢 Ставка {bet}⭐ проиграна (>10 мин)"

            # Increment streak and check for chest
            new_streak = db.increment_streak(student["id"])
            if new_streak % 5 == 0:
                chest_bonus = db.open_chest()
                db.add_bonus_points(student["id"], chest_bonus)
                chest_text = f"\n🎁 <b>СУНДУК! +{chest_bonus}⭐</b> (серия {new_streak})"

        # Show gamble option
        stats = (
            db.get_student_stats(student["id"]) if student["id"] != 0 else {"bonus_points": 0}
        )
        keyboard_rows = [
            [InlineKeyboardButton("🎉 К заданиям", callback_data="modules:list")],
            [InlineKeyboardButton("🏆 Лидерборд", callback_data="menu:leaderboard")],
        ]
        if stats["bonus_points"] >= 1:
            keyboard_rows.insert(
                0, [InlineKeyboardButton("🎲 Рискнуть 1⭐ (50/50)", callback_data="gamble:1")]
            )
        keyboard = InlineKeyboardMarkup(keyboard_rows)

        result = (
            f"✅ <b>Решено!</b> (#{sub_id}){timer_text}{bonus_text}{chest_text}\n\n"
            f"<pre>{safe_output}</pre>"
        )
    else:
        # Reset streak on failure
        if student["id"] != 0:
            db.reset_streak(student["id"])

        bet_text = ""
        if bet > 0:
            bet_text = f"\n😢 Ставка {bet}⭐ проиграна"

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔄 Ещё", callback_data=f"submit:{task_id}")],
                [InlineKeyboardButton("« Задание", callback_data=f"task:{task_id}")],
            ]
        )
        result = (
            f"❌ <b>Не пройдено</b> (#{sub_id}){timer_text}{bet_text}\n\n"
            f"<pre>{safe_output}</pre>"
        )
    await checking.edit_text(result, reply_markup=keyboard, parse_mode="HTML")
