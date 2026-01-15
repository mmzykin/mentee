"""Text message handler."""
import re
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from app.handlers.file_handler import process_submission
from app.notifications import notify_mentors, notify_student
from app.keyboards import back_to_admin_keyboard, back_to_menu_keyboard
from app.utils import escape_html, get_raw_text, parse_task_format, to_msk_str


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    # Use get_raw_text to preserve __name__, __init__ etc. in code
    text = get_raw_text(update.message).strip()

    if db.is_admin(user.id):
        if context.user_data.get("creating") == "module":
            parts = text.split()
            if len(parts) < 2:
                await update.message.reply_text(
                    "Формат: <code>id Название [go]</code>", parse_mode="HTML"
                )
                return
            module_id = parts[0]
            # Check if last part is language (only if 3+ parts to avoid "1 go" being empty name)
            if len(parts) >= 3 and parts[-1].lower() in ("go", "python", "py"):
                lang = "go" if parts[-1].lower() == "go" else "python"
                name = " ".join(parts[1:-1])
            else:
                lang = "python"
                name = " ".join(parts[1:])
            if db.add_module(module_id, name, len(db.get_modules()) + 1, lang):
                del context.user_data["creating"]
                lang_emoji = "🐹" if lang == "go" else "🐍"
                await update.message.reply_text(
                    f"✅ Модуль создан! {lang_emoji}", reply_markup=back_to_admin_keyboard()
                )
            else:
                await update.message.reply_text("❌ ID занят.")
            return

        if context.user_data.get("creating") == "topic":
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await update.message.reply_text(
                    "Формат: <code>id Название</code>", parse_mode="HTML"
                )
                return
            module_id = context.user_data.get("module_id", "1")
            if db.add_topic(
                parts[0], parts[1], module_id, len(db.get_topics_by_module(module_id)) + 1
            ):
                context.user_data.pop("creating", None)
                context.user_data.pop("module_id", None)
                await update.message.reply_text(
                    f"✅ Тема создана!", reply_markup=back_to_admin_keyboard()
                )
            else:
                await update.message.reply_text("❌ ID занят.")
            return

        if context.user_data.get("creating") == "task":
            parsed = parse_task_format(text)
            if not parsed:
                await update.message.reply_text("❌ Неверный формат.")
                return

            topic_id = parsed["topic_id"]
            topic = db.get_topic(topic_id)

            # Auto-create topic and module if not exists
            created_module = None
            created_topic = None
            if not topic:
                # Determine module from topic_id prefix
                prefix_to_module = {
                    "go_": ("go", "Go", "go"),
                    "python_": ("python", "Python", "python"),
                    "linux_": ("linux", "Linux", "other"),
                    "sql_": ("sql", "SQL & Базы данных", "other"),
                    "docker_": ("docker", "Docker & Контейнеры", "other"),
                    "git_": ("git", "Git & Version Control", "other"),
                    "network_": ("network", "Сети", "other"),
                    "algo_": ("algo", "Алгоритмы", "python"),
                    "system_": ("system", "System Design", "other"),
                    "web_": ("web", "Web & HTTP", "other"),
                }

                module_id = "other"
                module_name = "Другое"
                module_lang = parsed.get("language", "python")

                for prefix, (mod_id, mod_name, mod_lang_default) in prefix_to_module.items():
                    if topic_id.startswith(prefix):
                        module_id = mod_id
                        module_name = mod_name
                        module_lang = mod_lang_default
                        break

                # Create module if needed
                if not db.get_module(module_id):
                    db.add_module(module_id, module_name, order_num=100, language=module_lang)
                    created_module = module_name

                # Generate topic name from topic_id
                topic_name = topic_id.replace("_", " ").title()
                for prefix in prefix_to_module.keys():
                    if topic_id.startswith(prefix):
                        topic_name = topic_id[len(prefix) :].replace("_", " ").title()
                        break

                if not db.add_topic(topic_id, topic_name, module_id, order_num=0):
                    await update.message.reply_text(f"❌ Не удалось создать тему {topic_id}")
                    return
                topic = db.get_topic(topic_id)
                if not topic:
                    await update.message.reply_text(f"❌ Ошибка при создании темы {topic_id}")
                    return
                created_topic = topic_name

            lang = parsed.get("language", "python")
            if db.add_task(
                parsed["task_id"],
                topic_id,
                parsed["title"],
                parsed["description"],
                parsed["test_code"],
                lang,
            ):
                del context.user_data["creating"]
                lang_name = "Go 🐹" if lang == "go" else "Python 🐍"
                result_text = f"✅ Задание создано! ({lang_name})"
                if created_module:
                    result_text += f"\n📦 Создан модуль: <b>{escape_html(created_module)}</b>"
                if created_topic:
                    result_text += f"\n📁 Создана тема: <b>{escape_html(created_topic)}</b>"
                await update.message.reply_text(
                    result_text, reply_markup=back_to_admin_keyboard(), parse_mode="HTML"
                )
            else:
                await update.message.reply_text("❌ ID занят.")
            return

        if context.user_data.get("creating") == "announcement":
            if "---" not in text:
                await update.message.reply_text(
                    "❌ Нужен разделитель --- между заголовком и текстом"
                )
                return
            parts = text.split("---", 1)
            title = parts[0].strip()
            content = parts[1].strip() if len(parts) > 1 else ""
            if not title:
                await update.message.reply_text("❌ Заголовок не может быть пустым")
                return
            db.create_announcement(title, content, user.id)
            del context.user_data["creating"]

            # Send to all students
            students = db.get_active_students()
            sent_count = 0
            for s in students:
                try:
                    await context.bot.send_message(
                        s["user_id"],
                        f"📢 <b>Новое объявление!</b>\n\n"
                        f"<b>{escape_html(title)}</b>\n\n"
                        f"{escape_html(content)}",
                        parse_mode="HTML",
                    )
                    sent_count += 1
                except Exception:
                    pass
            await update.message.reply_text(
                f"✅ Объявление создано и отправлено {sent_count} студентам!",
                reply_markup=back_to_admin_keyboard(),
            )
            return

        if context.user_data.get("creating") == "meeting":
            lines = text.strip().split("\n")
            if len(lines) < 3:
                await update.message.reply_text("❌ Нужно 3 строки: название, ссылка, дата")
                return
            title = lines[0].strip()
            link = lines[1].strip()
            try:
                scheduled_at = datetime.strptime(lines[2].strip(), "%Y-%m-%d %H:%M").isoformat()
            except ValueError:
                await update.message.reply_text("❌ Неверный формат даты. Нужно: YYYY-MM-DD HH:MM")
                return

            context.user_data["meeting_data"] = {
                "title": title,
                "link": link,
                "scheduled_at": scheduled_at,
                "dt_str": lines[2].strip(),
            }
            context.user_data["creating"] = "meeting_duration"

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("15 мин", callback_data="meeting_dur:15"),
                        InlineKeyboardButton("30 мин", callback_data="meeting_dur:30"),
                    ],
                    [
                        InlineKeyboardButton("45 мин", callback_data="meeting_dur:45"),
                        InlineKeyboardButton("60 мин", callback_data="meeting_dur:60"),
                    ],
                    [
                        InlineKeyboardButton("90 мин", callback_data="meeting_dur:90"),
                        InlineKeyboardButton("120 мин", callback_data="meeting_dur:120"),
                    ],
                    [InlineKeyboardButton("❌ Отмена", callback_data="admin:meetings")],
                ]
            )

            await update.message.reply_text(
                f"📅 <b>{escape_html(title)}</b>\n"
                f"🕐 {lines[2].strip()}\n\n"
                f"<b>Выбери длительность созвона:</b>",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return

        if context.user_data.get("creating") == "meeting_approve":
            # Admin is approving a meeting request with telemost link
            meeting_id = context.user_data.get("approve_meeting_id")
            if not meeting_id:
                await update.message.reply_text("❌ Встреча не найдена")
                return

            link = text.strip()
            if not link.startswith("http"):
                await update.message.reply_text("❌ Отправь ссылку на Яндекс.Телемост")
                return

            meeting = db.get_meeting(meeting_id)
            if meeting:
                with db.get_db() as conn:
                    conn.execute(
                        "UPDATE meetings SET meeting_link = ?, status = 'confirmed' WHERE id = ?",
                        (link, meeting_id),
                    )

                # Notify student
                if meeting["student_id"]:
                    student = db.get_student_by_id(meeting["student_id"])
                    if student:
                        dt = to_msk_str(meeting["scheduled_at"])
                        try:
                            await context.bot.send_message(
                                student["user_id"],
                                f"✅ <b>Встреча подтверждена!</b>\n\n"
                                f"<b>{escape_html(meeting['title'])}</b>\n"
                                f"🕐 {dt}\n"
                                f"⏱ {meeting['duration_minutes']} мин\n\n"
                                f"🔗 <a href='{link}'>Открыть в Телемосте</a>\n\n"
                                f"Напоминание придёт за 24 часа и за 1 час.",
                                parse_mode="HTML",
                                disable_web_page_preview=True,
                            )
                        except Exception:
                            pass

            del context.user_data["creating"]
            context.user_data.pop("approve_meeting_id", None)
            await update.message.reply_text(
                "✅ Встреча подтверждена, ссылка отправлена студенту!",
                reply_markup=back_to_admin_keyboard(),
            )
            return

        if context.user_data.get("creating") == "meeting_slot_link":
            # Mentor entering telemost link after selecting time from slot
            meeting_id = context.user_data.get("slot_meeting_id")
            selected_time = context.user_data.get("slot_selected_time")

            if not meeting_id or not selected_time:
                await update.message.reply_text("❌ Данные не найдены")
                return

            link = text.strip()
            if not link.startswith("http"):
                await update.message.reply_text("❌ Отправь ссылку на Яндекс.Телемост")
                return

            meeting = db.get_meeting(meeting_id)
            if not meeting:
                await update.message.reply_text("❌ Встреча не найдена")
                return

            # Build confirmed time from date + selected time
            date_str = meeting["time_slot_start"][:10] if meeting.get("time_slot_start") else ""
            confirmed_time = f"{date_str}T{selected_time}:00"

            # Confirm meeting with selected time
            db.confirm_meeting_time(meeting_id, confirmed_time, link)

            # Notify student
            if meeting["student_id"]:
                student_obj = db.get_student_by_id(meeting["student_id"])
                if student_obj:
                    dt_formatted = f"{date_str} {selected_time}"
                    try:
                        await context.bot.send_message(
                            student_obj["user_id"],
                            f"✅ <b>Встреча подтверждена!</b>\n\n"
                            f"<b>{escape_html(meeting['title'])}</b>\n"
                            f"🕐 {dt_formatted}\n"
                            f"⏱ {meeting['duration_minutes']} мин\n\n"
                            f"🔗 <a href='{link}'>Открыть в Телемосте</a>\n\n"
                            f"Напоминание придёт за 24 часа и за 1 час.",
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                        )
                    except Exception:
                        pass

            del context.user_data["creating"]
            context.user_data.pop("slot_meeting_id", None)
            context.user_data.pop("slot_selected_time", None)
            await update.message.reply_text(
                "✅ Встреча подтверждена, ссылка отправлена студенту!",
                reply_markup=back_to_admin_keyboard(),
            )
            return

        if context.user_data.get("creating") == "question":
            parts = text.split("---")
            if len(parts) < 3:
                await update.message.reply_text(
                    "❌ Нужно разделить --- текст вопроса, варианты и ответ"
                )
                return

            topic_id = context.user_data.get("question_topic_id")
            if not topic_id:
                await update.message.reply_text("❌ Не выбрана тема")
                return

            question_text = parts[0].strip()
            options_text = parts[1].strip()
            answer_letter = parts[2].strip().upper()
            explanation = parts[3].strip() if len(parts) > 3 else None

            # Parse options
            options = []
            for line in options_text.split("\n"):
                line = line.strip()
                if line and len(line) > 2 and line[1] == ")":
                    options.append({"text": line[2:].strip()})

            if len(options) < 2:
                await update.message.reply_text("❌ Нужно минимум 2 варианта ответа")
                return

            # Find correct answer index
            letter_to_idx = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
            correct_idx = letter_to_idx.get(answer_letter, 0)
            if correct_idx >= len(options):
                correct_idx = 0

            q_id = db.add_question(topic_id, question_text, options, correct_idx, 0.1, explanation)
            del context.user_data["creating"]
            context.user_data.pop("question_topic_id", None)

            await update.message.reply_text(
                f"✅ Вопрос добавлен! (ID: {q_id})", reply_markup=back_to_admin_keyboard()
            )
            return

        if context.user_data.get("creating") == "questions_bulk":
            # Parse bulk questions format
            topic_match = re.search(r"TOPIC:\s*(\S+)", text)
            if not topic_match:
                await update.message.reply_text("❌ Не указан TOPIC")
                return
            topic_id = topic_match.group(1)
            topic = db.get_topic(topic_id)

            # Auto-create topic and module if not exists
            created_module = None
            created_topic = None
            if not topic:
                # Determine module from topic_id prefix
                prefix_to_module = {
                    "go_": ("go", "Go", "go"),
                    "python_": ("python", "Python", "python"),
                    "linux_": ("linux", "Linux", "other"),
                    "sql_": ("sql", "SQL & Базы данных", "other"),
                    "docker_": ("docker", "Docker & Контейнеры", "other"),
                    "git_": ("git", "Git & Version Control", "other"),
                    "network_": ("network", "Сети", "other"),
                    "algo_": ("algo", "Алгоритмы", "python"),
                    "system_": ("system", "System Design", "other"),
                    "web_": ("web", "Web & HTTP", "other"),
                }

                module_id = "other"
                module_name = "Другое"
                module_lang = "other"

                for prefix, (mod_id, mod_name, mod_lang) in prefix_to_module.items():
                    if topic_id.startswith(prefix):
                        module_id = mod_id
                        module_name = mod_name
                        module_lang = mod_lang
                        break

                # Create module if needed
                if not db.get_module(module_id):
                    db.add_module(module_id, module_name, order_num=100, language=module_lang)
                    created_module = module_name

                # Generate topic name from topic_id
                topic_name = topic_id.replace("_", " ").title()
                # Clean up prefix for better name
                for prefix in prefix_to_module.keys():
                    if topic_id.startswith(prefix):
                        topic_name = topic_id[len(prefix) :].replace("_", " ").title()
                        break

                if not db.add_topic(topic_id, topic_name, module_id, order_num=0):
                    await update.message.reply_text(f"❌ Не удалось создать тему {topic_id}")
                    return
                topic = db.get_topic(topic_id)
                if not topic:
                    await update.message.reply_text(f"❌ Ошибка при создании темы {topic_id}")
                    return
                created_topic = topic_name

            # Split by Q: marker
            questions_raw = re.split(r"\nQ:\s*", text)
            added = 0

            for q_raw in questions_raw[1:]:  # Skip first (before first Q:)
                lines = q_raw.strip().split("\n")
                if not lines:
                    continue

                question_text = lines[0].strip()
                options = []
                correct_idx = 0
                explanation = None

                for line in lines[1:]:
                    line = line.strip()
                    if line.startswith("ANSWER:"):
                        letter = line.split(":")[1].strip().upper()
                        correct_idx = {"A": 0, "B": 1, "C": 2, "D": 3}.get(letter, 0)
                    elif line.startswith("EXPLAIN:"):
                        explanation = line.split(":", 1)[1].strip()
                    elif len(line) > 2 and line[1] == ")":
                        options.append({"text": line[2:].strip()})

                if len(options) >= 2:
                    db.add_question(topic_id, question_text, options, correct_idx, 0.1, explanation)
                    added += 1

            del context.user_data["creating"]

            result_text = (
                f"✅ Импортировано <b>{added}</b> вопросов "
                f"в тему <b>{escape_html(topic['name'])}</b>!"
            )
            if created_module:
                result_text += f"\n📦 Создан модуль: <b>{escape_html(created_module)}</b>"
            if created_topic:
                result_text += f"\n📁 Создана тема: <b>{escape_html(created_topic)}</b>"

            await update.message.reply_text(
                result_text, reply_markup=back_to_admin_keyboard(), parse_mode="HTML"
            )
            return

        if context.user_data.get("feedback_for"):
            sub_id = context.user_data["feedback_for"]
            db.set_feedback(sub_id, text)
            del context.user_data["feedback_for"]
            await update.message.reply_text(
                f"💬 Фидбек сохранён для #{sub_id}!", reply_markup=back_to_admin_keyboard()
            )
            # Notify student about feedback
            sub = db.get_submission_by_id(sub_id)
            if sub:
                student = db.get_student_by_id(sub["student_id"])
                if student:
                    task = db.get_task(sub["task_id"])
                    task_name = task["title"] if task else sub["task_id"]
                    await notify_student(
                        context,
                        student["user_id"],
                        f"💬 <b>Новый фидбек от ментора!</b>\n\n"
                        f"Задание: <b>{escape_html(task_name)}</b>\n\n"
                        f"{escape_html(text)}",
                    )
            return

        if context.user_data.get("editing_student_name"):
            student_id = context.user_data["editing_student_name"]
            db.update_student_name(student_id, text)
            del context.user_data["editing_student_name"]
            await update.message.reply_text(
                f"✅ Имя изменено на: {escape_html(text)}", reply_markup=back_to_admin_keyboard()
            )
            return

        if context.user_data.get("archiving_student"):
            student_id = context.user_data["archiving_student"]
            reason = context.user_data.get("archive_reason", "HIRED")
            db.archive_student(student_id, reason, text)
            del context.user_data["archiving_student"]
            context.user_data.pop("archive_reason", None)
            await update.message.reply_text(
                f"✅ Студент архивирован!\n\n💬 Отзыв сохранён.",
                reply_markup=back_to_admin_keyboard(),
            )
            return

    # Student meeting request with time slot (outside admin block)
    if context.user_data.get("creating") == "meeting_request":
        student = db.get_student(user.id)
        if not student:
            await update.message.reply_text("⛔ Нужна регистрация")
            return

        lines = text.strip().split("\n")
        if len(lines) < 4:
            await update.message.reply_text(
                "❌ Нужно 4 строки:\n"
                "1. Тема встречи\n"
                "2. Дата (YYYY-MM-DD)\n"
                "3. Интервал (HH:MM-HH:MM)\n"
                "4. Длительность в минутах"
            )
            return

        title = lines[0].strip()
        date_str = lines[1].strip()
        time_slot = lines[2].strip()

        # Validate date
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text("❌ Неверный формат даты. Нужно: YYYY-MM-DD")
            return

        # Parse time slot (e.g., "16:00-21:00")
        slot_match = re.match(r"^(\d{1,2}:\d{2})-(\d{1,2}:\d{2})$", time_slot)
        if not slot_match:
            await update.message.reply_text(
                "❌ Неверный формат интервала. "
                "Нужно: HH:MM-HH:MM (например, 16:00-21:00)"
            )
            return

        time_start = slot_match.group(1)
        time_end = slot_match.group(2)

        # Validate times
        try:
            start_dt = datetime.strptime(f"{date_str} {time_start}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{date_str} {time_end}", "%Y-%m-%d %H:%M")
            if end_dt <= start_dt:
                await update.message.reply_text(
                    "❌ Конец интервала должен быть позже начала")
                return
        except ValueError:
            await update.message.reply_text("❌ Неверный формат времени")
            return

        # Parse duration
        try:
            duration = int(lines[3].strip())
            if duration < 15 or duration > 180:
                await update.message.reply_text(
                    "❌ Длительность должна быть от 15 до 180 минут")
                return
        except ValueError:
            await update.message.reply_text(
                "❌ Длительность должна быть числом (минуты)")
            return

        # Create meeting with time slot
        meeting_id = db.create_meeting_with_slot(
            student["id"], title, date_str, time_start, time_end, duration, student["user_id"]
        )

        del context.user_data["creating"]

        # Notify assigned mentors
        student_name = student.get("first_name") or student.get("username") or "?"

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🕐 Выбрать время", callback_data=f"meeting_slot:{meeting_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Отклонить", callback_data=f"meeting_reject:{meeting_id}"
                    )
                ],
            ]
        )

        await notify_mentors(
            context,
            student["id"],
            f"🔔 <b>Запрос на встречу!</b>\n\n"
            f"👤 От: <b>{escape_html(student_name)}</b>\n"
            f"📋 Тема: <b>{escape_html(title)}</b>\n"
            f"📅 Дата: {date_str}\n"
            f"🕐 Удобное время: {time_start} — {time_end}\n"
            f"⏱ {duration} мин\n\n"
            f"<i>Выберите конкретное время для встречи</i>",
            keyboard=keyboard,
        )

        await update.message.reply_text(
            f"✅ Запрос отправлен ментору!\n\n"
            f"📋 {escape_html(title)}\n"
            f"📅 {date_str}\n"
            f"🕐 Интервал: {time_start} — {time_end}\n"
            f"⏱ {duration} мин\n\n"
            f"<i>Ментор выберет удобное время и подтвердит встречу</i>",
            parse_mode="HTML",
        )
        return

    task_id = context.user_data.get("pending_task")
    if task_id:
        await process_submission(update, context, text)
