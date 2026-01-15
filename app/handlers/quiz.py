"""Quiz handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from app.keyboards import back_to_menu_keyboard
from app.utils import escape_html, safe_answer, to_msk_str


async def quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    student = db.get_student(user.id)

    if not student:
        await query.edit_message_text("⛔ Нужна регистрация", reply_markup=back_to_menu_keyboard())
        return

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "menu"

    if action == "menu":
        total_questions = db.get_all_questions_count()
        history = db.get_student_quiz_history(student["id"], 5)

        text = "❓ <b>Вопросы с собеседований</b>\n\n"
        text += f"Всего вопросов: <b>{total_questions}</b>\n\n"

        if history:
            text += "<b>Последние попытки:</b>\n"
            for h in history:
                date = to_msk_str(h["started_at"], date_only=True)
                score = f"{h['correct_answers']}/{h['total_questions']}"
                points = f"+{h['points_earned']:.1f}"
                status = "✅" if h["status"] == "finished" else "⏳"
                text += f"{status} [{date}] {score} ({points})\n"

        keyboard = [
            [InlineKeyboardButton("🎲 Рандом 20 вопросов", callback_data="quiz:start_random")],
            [InlineKeyboardButton("📚 По теме", callback_data="quiz:select_topic")],
            [InlineKeyboardButton("« Главное меню", callback_data="menu:main")],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    elif action == "select_topic":
        topics = db.get_topics()
        keyboard = []
        for t in topics:
            count = db.get_questions_count_by_topic(t["topic_id"])
            if count > 0:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"📚 {t['name']} ({count})",
                            callback_data=f"quiz:start_topic:{t['topic_id']}",
                        )
                    ]
                )
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="quiz:menu")])
        await query.edit_message_text(
            "Выбери тему:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    elif action == "start_random":
        questions = db.get_random_questions(20)
        if len(questions) < 5:
            await query.edit_message_text(
                "Недостаточно вопросов. Минимум 5.", reply_markup=back_to_menu_keyboard()
            )
            return

        session_id = db.start_quiz_session(student["id"], questions, time_limit_seconds=600)
        context.user_data["quiz_session"] = session_id
        await show_quiz_question(query, context, session_id)

    elif action == "start_topic":
        topic_id = parts[2]
        questions = db.get_random_questions(20, topic_id=topic_id)
        if len(questions) < 3:
            await query.edit_message_text(
                "Недостаточно вопросов в этой теме.", reply_markup=back_to_menu_keyboard()
            )
            return

        session_id = db.start_quiz_session(student["id"], questions, time_limit_seconds=600)
        context.user_data["quiz_session"] = session_id
        await show_quiz_question(query, context, session_id)

    elif action == "answer":
        session_id = context.user_data.get("quiz_session")
        if not session_id:
            await query.edit_message_text(
                "Сессия не найдена.", reply_markup=back_to_menu_keyboard()
            )
            return

        # Check if expired
        if db.is_quiz_expired(session_id):
            result = db.finish_quiz_session(session_id)
            context.user_data.pop("quiz_session", None)
            await show_quiz_results(query, result)
            return

        question_id = int(parts[2])
        option_id = int(parts[3])

        answer_result = db.answer_quiz_question(session_id, question_id, option_id)

        # Show brief feedback and next question
        await show_quiz_question(
            query, context, session_id, last_correct=answer_result["is_correct"]
        )

    elif action == "finish":
        session_id = context.user_data.get("quiz_session")
        if session_id:
            result = db.finish_quiz_session(session_id)
            context.user_data.pop("quiz_session", None)
            await show_quiz_results(query, result)


async def show_quiz_question(query, context, session_id, last_correct=None):
    """Show current quiz question."""
    q = db.get_quiz_current_question(session_id)

    if not q:
        # No more questions - finish quiz
        result = db.finish_quiz_session(session_id)
        context.user_data.pop("quiz_session", None)
        await show_quiz_results(query, result)
        return

    session = db.get_quiz_session(session_id)
    remaining = db.get_quiz_time_remaining(session_id)
    mins, secs = divmod(remaining, 60)

    answered = sum(1 for a in session["answers"] if a.get("selected_option_id"))
    total = session["total_questions"]

    text = f"❓ <b>Вопрос {answered + 1}/{total}</b>\n"
    text += f"⏱ Осталось: {mins}:{secs:02d}\n\n"

    if last_correct is not None:
        text += "✅ Верно!\n\n" if last_correct else "❌ Неверно\n\n"

    text += f"<b>{escape_html(q['question_text'])}</b>\n\n"

    letters = ["A", "B", "C", "D", "E"]
    keyboard = []
    for i, opt in enumerate(q["options"]):
        letter = letters[i] if i < len(letters) else str(i + 1)
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{letter}) {opt['option_text'][:50]}",
                    callback_data=f"quiz:answer:{q['question_id']}:{opt['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⏹ Завершить досрочно", callback_data="quiz:finish")])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def show_quiz_results(query, result):
    """Show quiz results."""
    if not result:
        await query.edit_message_text(
            "Ошибка получения результатов.", reply_markup=back_to_menu_keyboard()
        )
        return

    correct = result.get("correct_answers", 0)
    total = result.get("total_questions", 0)
    points = result.get("points_earned", 0)
    percent = (correct / total * 100) if total > 0 else 0

    if percent >= 80:
        grade = "🏆 Отлично!"
    elif percent >= 60:
        grade = "👍 Хорошо"
    elif percent >= 40:
        grade = "📚 Неплохо, но повтори материал"
    else:
        grade = "📖 Нужно больше практики"

    text = f"🎯 <b>Результаты квиза</b>\n\n"
    text += f"Правильных: <b>{correct}/{total}</b> ({percent:.0f}%)\n"
    text += f"Заработано: <b>+{int(points)}</b> баллов\n\n"
    text += f"{grade}"

    keyboard = [
        [InlineKeyboardButton("🔄 Ещё раз", callback_data="quiz:menu")],
        [InlineKeyboardButton("« Главное меню", callback_data="menu:main")],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )
