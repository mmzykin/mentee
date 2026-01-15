"""Admin handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from app.config import BONUS_POINTS_PER_APPROVAL
from app.decorators import require_admin
from app.keyboards import admin_menu_keyboard, back_to_admin_keyboard
from app.notifications import notify_student
from app.utils import escape_html, safe_answer, to_msk_str


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    action = query.data.split(":")[1]

    if action == "mystudents":
        admin_id = update.effective_user.id
        my_students = db.get_mentor_students(admin_id)

        if not my_students:
            text = (
                "🎓 <b>Мои ученики</b>\n\n"
                "<i>У вас нет назначенных учеников.</i>\n\n"
                "Чтобы назначить себя ментором ученика, "
                "откройте его профиль в разделе «Студенты» "
                "и нажмите «Менторы»."
            )
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Админ", callback_data="menu:admin")]]
            )
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
            return

        text = f"🎓 <b>Мои ученики ({len(my_students)})</b>\n\n"
        keyboard = []
        for s in my_students:
            name = s.get("first_name") or s.get("username") or "?"
            stats = db.get_student_stats(s["id"])
            btn_text = f"👤 {name} | ✅{stats['solved_tasks']} ⭐{stats['bonus_points']}"
            keyboard.append(
                [InlineKeyboardButton(btn_text, callback_data=f"student:{s['user_id']}")]
            )

        keyboard.append([InlineKeyboardButton("« Админ", callback_data="menu:admin")])
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    elif action == "modules":
        modules = db.get_modules()
        text = "📦 <b>Модули</b>\n\n"
        if modules:
            for m in modules:
                topics_count = len(db.get_topics_by_module(m["module_id"]))
                text += (
                    f"• <code>{m['module_id']}</code>: {escape_html(m['name'])} "
                    f"({topics_count} тем)\n"
                )
        else:
            text += "<i>Пусто</i>\n"
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ Добавить модуль", callback_data="create:module")],
                [InlineKeyboardButton("« Админ", callback_data="menu:admin")],
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "topics":
        modules = db.get_modules()
        text = "📚 <b>Темы</b>\n\n"
        for m in modules:
            topics = db.get_topics_by_module(m["module_id"])
            text += f"<b>{escape_html(m['name'])}</b>\n"
            if topics:
                for t in topics:
                    count = len(db.get_tasks_by_topic(t["topic_id"]))
                    text += (
                        f"  • <code>{t['topic_id']}</code>: {escape_html(t['name'])} "
                        f"({count})\n"
                    )
            else:
                text += "  <i>(пусто)</i>\n"
            text += "\n"
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ Добавить тему", callback_data="create:topic_select")],
                [InlineKeyboardButton("« Админ", callback_data="menu:admin")],
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "tasks":
        text = "📝 <b>Задания</b>\n\nНажми на задание для управления:\n\n"
        keyboard = []
        for topic in db.get_topics():
            tasks = db.get_tasks_by_topic(topic["topic_id"])
            if tasks:
                for t in tasks:
                    lang = t.get("language", "python")
                    emoji = "🐹" if lang == "go" else "🐍"
                    btn_text = f"{emoji} {t['task_id']}: {t['title'][:25]}"
                    keyboard.append(
                        [InlineKeyboardButton(btn_text, callback_data=f"admintask:{t['task_id']}")]
                    )
        if not keyboard:
            text += "<i>Пусто</i>\n"
        keyboard.append([InlineKeyboardButton("➕ Добавить задание", callback_data="create:task")])
        keyboard.append([InlineKeyboardButton("« Админ", callback_data="menu:admin")])
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    elif action == "students":
        students = db.get_active_students_stats()
        archived = db.get_archived_students()
        if not students and not archived:
            await query.edit_message_text("Нет студентов.", reply_markup=back_to_admin_keyboard())
            return
        keyboard = []
        for s in students:
            name = s.get("first_name") or s.get("username") or "?"
            btn = f"{name}: {s['solved_tasks']}/{s['total_tasks']} +{s['bonus_points']}⭐"
            keyboard.append([InlineKeyboardButton(btn, callback_data=f"student:{s['user_id']}")])
        if archived:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"🎓 Выпускники ({len(archived)})", callback_data="admin:archived"
                    )
                ]
            )
        keyboard.append([InlineKeyboardButton("« Админ", callback_data="menu:admin")])
        text = f"👥 <b>Активные студенты</b> ({len(students)})"
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    elif action == "archived":
        archived = db.get_archived_students()
        if not archived:
            await query.edit_message_text("Нет выпускников.", reply_markup=back_to_admin_keyboard())
            return
        keyboard = []
        for s in archived:
            name = s.get("first_name") or s.get("username") or "?"
            reason = s.get("archive_reason", "")
            btn = f"🎓 {name} ({reason})"
            keyboard.append(
                [InlineKeyboardButton(btn, callback_data=f"archived_student:{s['user_id']}")]
            )
        keyboard.append([InlineKeyboardButton("« Студенты", callback_data="admin:students")])
        await query.edit_message_text(
            "🎓 <b>Выпускники</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    elif action == "codes":
        codes = db.get_unused_codes()
        text = f"🎫 <b>Коды</b> ({len(codes)})\n\n" if codes else "<i>Нет кодов.</i>"
        for c in codes[:20]:
            text += f"<code>{c['code']}</code>\n"
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ Создать 5", callback_data="admin:gencodes")],
                [InlineKeyboardButton("« Админ", callback_data="menu:admin")],
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "gencodes":
        codes = db.create_codes(5)
        text = "🎫 <b>Созданы</b>\n\n" + "\n".join(f"<code>{c}</code>" for c in codes)
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ Ещё 5", callback_data="admin:gencodes")],
                [InlineKeyboardButton("« Админ", callback_data="menu:admin")],
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "cleanup":
        deleted = db.cleanup_old_code()
        await query.edit_message_text(
            f"🧹 Удалено кода из <b>{deleted}</b> отправок.",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="HTML",
        )

    elif action == "announcements":
        announcements = db.get_announcements(10)
        text = "📢 <b>Объявления</b>\n\n"
        if announcements:
            for a in announcements:
                date = to_msk_str(a["created_at"], date_only=True)
                text += f"• [{date}] <b>{escape_html(a['title'])}</b>\n"
        else:
            text += "<i>Пока нет объявлений</i>\n"
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ Новое объявление", callback_data="create:announcement")],
                [InlineKeyboardButton("« Админ", callback_data="menu:admin")],
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "meetings":
        meetings = db.get_meetings(include_past=False)
        text = "📅 <b>Запланированные встречи</b>\n\n"
        if meetings:
            for m in meetings:
                student = db.get_student_by_id(m["student_id"]) if m["student_id"] else None
                student_name = (
                    (student.get("first_name") or student.get("username") or "?")
                    if student
                    else "Не назначен"
                )
                dt = to_msk_str(m["scheduled_at"])
                status_emoji = {"pending": "⏳", "confirmed": "✅", "cancelled": "❌"}.get(
                    m["status"], "⏳"
                )
                text += f"{status_emoji} <b>{escape_html(m['title'])}</b>\n"
                text += f"   👤 {student_name} | 🕐 {dt}\n\n"
        else:
            text += "<i>Нет запланированных встреч</i>\n"
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ Назначить встречу", callback_data="create:meeting")],
                [
                    InlineKeyboardButton("📋 Все встречи", callback_data="meetings:all"),
                    InlineKeyboardButton("🔗 Ссылки", callback_data="meetings:links"),
                ],
                [InlineKeyboardButton("« Админ", callback_data="menu:admin")],
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "questions":
        total = db.get_all_questions_count()
        text = f"❓ <b>Вопросы с собеседований</b>\n\nВсего: <b>{total}</b> вопросов\n\n"
        topics = db.get_topics()
        if topics:
            text += "<b>По темам:</b>\n"
            for t in topics[:15]:
                count = db.get_questions_count_by_topic(t["topic_id"])
                if count > 0:
                    text += f"• {escape_html(t['name'])}: {count}\n"
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ Добавить вопрос", callback_data="create:question")],
                [InlineKeyboardButton("📥 Импорт вопросов", callback_data="create:questions_bulk")],
                [InlineKeyboardButton("« Админ", callback_data="menu:admin")],
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


async def create_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "module":
        context.user_data["creating"] = "module"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="admin:modules")]]
        )
        await query.edit_message_text(
            "📦 <b>Новый модуль</b>\n\n"
            "Отправь ID, название и язык (опционально):\n"
            "<code>2 ООП</code> — Python по умолчанию\n"
            "<code>go1 Основы Go go</code> — для Go модуля",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    elif action == "topic_select":
        modules = db.get_modules()
        if not modules:
            await query.edit_message_text(
                "Сначала создай модуль.", reply_markup=back_to_admin_keyboard()
            )
            return
        keyboard = [
            [
                InlineKeyboardButton(
                    f"📦 {m['name']}", callback_data=f"create:topic:{m['module_id']}"
                )
            ]
            for m in modules
        ]
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="admin:topics")])
        await query.edit_message_text(
            "Выбери модуль для темы:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "topic" and len(parts) > 2:
        module_id = parts[2]
        module = db.get_module(module_id)
        if not module:
            await query.edit_message_text("Модуль не найден.")
            return
        context.user_data["creating"] = "topic"
        context.user_data["module_id"] = module_id
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="admin:topics")]]
        )
        await query.edit_message_text(
            f"📚 <b>Новая тема в {escape_html(module['name'])}</b>\n\n"
            f"Отправь ID и название:\n<code>2.1 Классы</code>",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    elif action == "task":
        topics = db.get_topics()
        context.user_data["creating"] = "task"
        text = "📝 <b>Новое задание</b>\n\n"
        if topics:
            text += "Существующие темы:\n"
            for t in topics[:10]:
                text += f"• <code>{t['topic_id']}</code>: {escape_html(t['name'])}\n"
            text += "\n"
        text += "💡 <i>Если темы нет — она создастся автоматически!</i>\n"
        text += "Префиксы: go_, python_, linux_, sql_, docker_, git_\n\n"
        text += (
            "Отправь в формате:\n<code>TOPIC: go_basics\nTASK_ID: task_id\n"
            "TITLE: Название\nLANGUAGE: go\n---DESCRIPTION---\nОписание\n"
            "---TESTS---\nfunc Test... или def test(): ...</code>"
        )
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="admin:tasks")]]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "announcement":
        # Clear any pending feedback to avoid conflicts
        context.user_data.pop("feedback_for", None)
        context.user_data["creating"] = "announcement"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="admin:announcements")]]
        )
        await query.edit_message_text(
            "📢 <b>Новое объявление</b>\n\n"
            "Отправь в формате:\n"
            "<code>Заголовок\n---\nТекст объявления</code>\n\n"
            "Первая строка — заголовок, после --- идёт текст.",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    elif action == "meeting":
        students = db.get_active_students()
        if not students:
            await query.edit_message_text(
                "Нет активных студентов.", reply_markup=back_to_admin_keyboard()
            )
            return
        keyboard = [
            [
                InlineKeyboardButton(
                    f"👤 {s.get('first_name') or s.get('username') or '?'}",
                    callback_data=f"create:meeting_student:{s['id']}",
                )
            ]
            for s in students
        ]
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="admin:meetings")])
        await query.edit_message_text(
            "📅 <b>Новая встреча</b>\n\nВыбери студента:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )

    elif action == "meeting_student":
        student_id = int(parts[2])
        student = db.get_student_by_id(student_id)
        if not student:
            await query.edit_message_text(
                "Студент не найден.", reply_markup=back_to_admin_keyboard()
            )
            return
        context.user_data["creating"] = "meeting"
        context.user_data["meeting_student_id"] = student_id
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="admin:meetings")]]
        )
        name = student.get("first_name") or student.get("username") or "?"
        await query.edit_message_text(
            f"📅 <b>Встреча с {escape_html(name)}</b>\n\n"
            "Отправь данные в формате:\n"
            "<code>Пробное собеседование\n"
            "https://telemost.yandex.ru/j/xxx\n"
            "2026-01-15 18:00</code>\n\n"
            "Строки:\n"
            "1. Название встречи\n"
            "2. Ссылка на Яндекс.Телемост\n"
            "3. Дата и время (YYYY-MM-DD HH:MM)\n\n"
            "<i>Длительность выберешь на следующем шаге</i>",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    elif action == "question":
        topics = db.get_topics()
        if not topics:
            await query.edit_message_text(
                "Сначала создай тему.", reply_markup=back_to_admin_keyboard()
            )
            return
        keyboard = [
            [
                InlineKeyboardButton(
                    f"📚 {t['name']}", callback_data=f"create:question_topic:{t['topic_id']}"
                )
            ]
            for t in topics[:20]
        ]
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="admin:questions")])
        await query.edit_message_text(
            "❓ <b>Новый вопрос</b>\n\nВыбери тему:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )

    elif action == "question_topic":
        topic_id = parts[2]
        topic = db.get_topic(topic_id)
        if not topic:
            await query.edit_message_text("Тема не найдена.", reply_markup=back_to_admin_keyboard())
            return
        context.user_data["creating"] = "question"
        context.user_data["question_topic_id"] = topic_id
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="admin:questions")]]
        )
        await query.edit_message_text(
            f"❓ <b>Вопрос в тему: {escape_html(topic['name'])}</b>\n\n"
            "Отправь в формате:\n"
            "<code>Текст вопроса?\n"
            "---\n"
            "A) Вариант 1\n"
            "B) Вариант 2\n"
            "C) Вариант 3\n"
            "D) Вариант 4\n"
            "---\n"
            "B\n"
            "---\n"
            "Объяснение (необязательно)</code>\n\n"
            "Правильный ответ — буква (A/B/C/D).",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    elif action == "questions_bulk":
        context.user_data["creating"] = "questions_bulk"
        topics = db.get_topics()
        text = "📥 <b>Импорт вопросов</b>\n\n"
        if topics:
            text += "Существующие темы:\n"
            for t in topics[:10]:
                text += f"• <code>{t['topic_id']}</code>: {escape_html(t['name'])}\n"
            text += "\n"
        text += "💡 <i>Если темы нет — она создастся автоматически!</i>\n"
        text += "Префиксы: go_, python_, linux_, sql_, docker_, git_\n\n"
        text += "Отправь вопросы в формате:\n"
        text += "<code>TOPIC: go_basics\n\n"
        text += "Q: Текст вопроса?\n"
        text += "A) Вариант 1\n"
        text += "B) Вариант 2\n"
        text += "C) Правильный вариант\n"
        text += "D) Вариант 4\n"
        text += "ANSWER: C\n"
        text += "EXPLAIN: Объяснение\n\n"
        text += "Q: Следующий вопрос?...</code>"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="admin:questions")]]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


async def student_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    context.user_data.pop("editing_student_name", None)
    context.user_data.pop("archiving_student", None)
    context.user_data.pop("archive_reason", None)
    user_id = int(query.data.split(":")[1])
    student = db.get_student(user_id)
    if not student:
        await query.edit_message_text("Не найден.")
        return
    name = escape_html(student.get("first_name") or student.get("username") or "?")
    username = f"@{student.get('username')}" if student.get("username") else "нет username"
    stats = db.get_student_stats(student["id"])
    assigned = db.get_assigned_tasks(student["id"])
    mentors = db.get_student_mentors(student["id"])
    admins = db.get_all_admins()
    admin_names = {a["user_id"]: a.get("name") or f"ID:{a['user_id']}" for a in admins}

    mentors_text = ""
    if mentors:
        mentor_list = [
            admin_names.get(m["mentor_user_id"], f"ID:{m['mentor_user_id']}") for m in mentors
        ]
        mentors_text = f"\n👨‍🏫 Менторы: {', '.join(mentor_list)}"
    else:
        mentors_text = "\n👨‍🏫 Менторы: <i>не назначены</i>"

    text = (
        f"📋 <b>{name}</b>\n"
        f"👤 {username}\n"
        f"ID: <code>{user_id}</code>\n\n"
        f"✅ {stats['solved_tasks']}/{stats['total_tasks']}\n"
        f"⭐ Бонусов: {stats['bonus_points']}\n"
        f"📌 Назначено: {len(assigned)}"
        f"{mentors_text}"
    )
    keyboard = [
        [InlineKeyboardButton("📋 Последние 10 попыток", callback_data=f"recent:{student['id']}")],
        [InlineKeyboardButton("📝 По заданиям", callback_data=f"bytask:{student['id']}")],
        [InlineKeyboardButton("📌 Назначить задание", callback_data=f"assign:{student['id']}")],
        [InlineKeyboardButton("👨‍🏫 Менторы", callback_data=f"mentors:{student['id']}")],
        [InlineKeyboardButton("✏️ Изменить имя", callback_data=f"editname:{student['id']}")],
        [InlineKeyboardButton("🎉 Устроен на работу", callback_data=f"hired:{student['id']}")],
        [InlineKeyboardButton("« Студенты", callback_data="admin:students")],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def recent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    student_id = int(query.data.split(":")[1])
    student = db.get_student_by_id(student_id)
    if not student:
        await query.edit_message_text("Не найден.")
        return
    subs = db.get_recent_submissions(student_id, 10)
    name = escape_html(student.get("first_name") or "?")
    text = f"📋 <b>{name}</b> — последние попытки\n\n"
    keyboard = []
    for sub in subs:
        status = "✅" if sub["passed"] else "❌"
        approved = "⭐" if sub.get("approved") else ""
        feedback = "💬" if sub.get("feedback") else ""
        date = to_msk_str(sub["submitted_at"])
        btn = f"{status}{approved}{feedback} #{sub['id']} {sub['task_id']} {date}"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"code:{sub['id']}")])
    keyboard.append(
        [InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")]
    )
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def bytask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    student_id = int(query.data.split(":")[1])
    student = db.get_student_by_id(student_id)
    if not student:
        await query.edit_message_text("Не найден.")
        return
    name = escape_html(student.get("first_name") or "?")
    text = f"📋 <b>{name}</b> — по заданиям\n\n"
    keyboard = []
    for topic in db.get_topics():
        for task in db.get_tasks_by_topic(topic["topic_id"]):
            subs = db.get_student_submissions(student_id, task["task_id"])
            if subs:
                solved = db.has_solved(student_id, task["task_id"])
                status = "✅" if solved else "❌"
                btn = f"{status} {task['task_id']}: {len(subs)} попыт."
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            btn, callback_data=f"attempts:{student_id}:{task['task_id']}"
                        )
                    ]
                )
    if not keyboard:
        text += "<i>Нет попыток</i>"
    keyboard.append(
        [InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")]
    )
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def attempts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    parts = query.data.split(":")
    student_id = int(parts[1])
    task_id = parts[2]
    student = db.get_student_by_id(student_id)
    task = db.get_task(task_id)
    subs = db.get_student_submissions(student_id, task_id)
    name = escape_html(student.get("first_name") or "?") if student else "?"
    title = escape_html(task["title"]) if task else task_id
    text = f"📝 <b>{title}</b>\n👤 {name}\n\n"
    keyboard = []
    for sub in subs:
        status = "✅" if sub["passed"] else "❌"
        approved = "⭐" if sub.get("approved") else ""
        feedback = "💬" if sub.get("feedback") else ""
        date = to_msk_str(sub["submitted_at"])
        btn = f"{status}{approved}{feedback} #{sub['id']} {date}"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"code:{sub['id']}")])
    keyboard.append(
        [InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")]
    )
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    sub_id = int(query.data.split(":")[1])
    sub = db.get_submission_by_id(sub_id)
    if not sub:
        await query.edit_message_text("Не найден.")
        return

    # Check if already marked as cheated
    is_cheated = sub.get("feedback") and "🚨 СПИСАНО" in sub.get("feedback", "")

    status = "🚨" if is_cheated else ("✅" if sub["passed"] else "❌")
    approved = " ⭐Аппрувнуто" if sub.get("approved") else ""
    code = sub["code"] or "[удалён]"
    if len(code) > 2500:
        code = code[:2500] + "\n...(обрезано)"
    text = (
        f"<b>{status}{approved}</b>\nID: <code>#{sub['id']}</code>\n"
        f"Задание: <code>{sub['task_id']}</code>\n"
        f"Время: {to_msk_str(sub['submitted_at'])}\n\n<pre>{escape_html(code)}</pre>"
    )
    if sub.get("feedback"):
        text += f"\n\n💬 <b>Фидбек:</b>\n{escape_html(sub['feedback'])}"

    # Show student's current bonus
    student = db.get_student_by_id(sub["student_id"])
    if student:
        bonus = db.get_student_bonus(student["id"])
        text += f"\n\n👤 Баланс студента: <b>{bonus}⭐</b>"

    keyboard = []
    row1 = []
    if not sub.get("approved") and not is_cheated:
        # Allow approval for both passed and failed
        row1.append(InlineKeyboardButton("⭐ Аппрув", callback_data=f"approve:{sub_id}"))
    elif sub.get("approved"):
        row1.append(InlineKeyboardButton("❌ Убрать аппрув", callback_data=f"unapprove:{sub_id}"))
    row1.append(InlineKeyboardButton("💬 Фидбек", callback_data=f"feedback:{sub_id}"))
    keyboard.append(row1)

    # GOD MODE - Cheater punishment (only for passed solutions that aren't already marked)
    if sub["passed"] and not is_cheated:
        keyboard.append(
            [
                InlineKeyboardButton("🚨 Списал!", callback_data=f"cheater:{sub_id}:0"),
                InlineKeyboardButton("🚨 -1⭐", callback_data=f"cheater:{sub_id}:1"),
                InlineKeyboardButton("🚨 -3⭐", callback_data=f"cheater:{sub_id}:3"),
                InlineKeyboardButton("🚨 -5⭐", callback_data=f"cheater:{sub_id}:5"),
            ]
        )

    keyboard.append([InlineKeyboardButton("🗑 Удалить", callback_data=f"delsub:{sub_id}")])
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"recent:{sub['student_id']}")])
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await safe_answer(query, "⛔")
        return
    sub_id = int(query.data.split(":")[1])
    sub = db.get_submission_by_id(sub_id)
    was_failed = sub and not sub["passed"]
    if db.approve_submission(sub_id, BONUS_POINTS_PER_APPROVAL):
        await safe_answer(query, "⭐ Аппрувнуто!", show_alert=True)
        # Notify student
        if sub:
            student = db.get_student_by_id(sub["student_id"])
            if student:
                task = db.get_task(sub["task_id"])
                task_name = task["title"] if task else sub["task_id"]
                # Different message if we're approving a failed submission
                if was_failed:
                    msg = (
                        f"⭐ <b>Ваше решение засчитано вручную!</b>\n\n"
                        f"Задание: <b>{escape_html(task_name)}</b>\n"
                        f"Ментор проверил и подтвердил правильность.\n"
                        f"Вы получили +{BONUS_POINTS_PER_APPROVAL} бонус!"
                    )
                else:
                    msg = (
                        f"⭐ <b>Ваше решение аппрувнуто!</b>\n\n"
                        f"Задание: <b>{escape_html(task_name)}</b>\n"
                        f"Вы получили +{BONUS_POINTS_PER_APPROVAL} бонус!"
                    )
                await notify_student(context, student["user_id"], msg)
    else:
        await safe_answer(query, "Уже или ошибка.", show_alert=True)
    await code_callback(update, context)


async def unapprove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await safe_answer(query, "⛔")
        return
    sub_id = int(query.data.split(":")[1])
    db.unapprove_submission(sub_id)
    await safe_answer(query, "Отменено.", show_alert=True)
    await code_callback(update, context)


async def admintask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin task management - view/delete tasks."""
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return

    parts = query.data.split(":")
    action = parts[0]
    task_id = parts[1] if len(parts) > 1 else None

    if action == "admintask" and task_id:
        task = db.get_task(task_id)
        if not task:
            await query.edit_message_text(
                "Задание не найдено.", reply_markup=back_to_admin_keyboard()
            )
            return

        lang = task.get("language", "python")
        lang_label = "🐹 Go" if lang == "go" else "🐍 Python"
        desc = escape_html(task["description"][:500])
        if len(task["description"]) > 500:
            desc += "..."

        text = (
            f"📝 <b>{escape_html(task['title'])}</b>\n"
            f"ID: <code>{task_id}</code> • {lang_label}\n"
            f"Тема: <code>{task['topic_id']}</code>\n\n"
            f"<b>Описание:</b>\n<pre>{desc}</pre>"
        )

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🗑 Удалить задание", callback_data=f"deltask:{task_id}")],
                [InlineKeyboardButton("« Задания", callback_data="admin:tasks")],
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "deltask" and task_id:
        task = db.get_task(task_id)
        if not task:
            await query.edit_message_text(
                "Задание не найдено.", reply_markup=back_to_admin_keyboard()
            )
            return

        text = (
            f"⚠️ <b>Удалить задание?</b>\n\n"
            f"<code>{task_id}</code>: {escape_html(task['title'])}\n\n"
            f"Это действие необратимо!"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Да, удалить", callback_data=f"deltask_confirm:{task_id}"
                    ),
                    InlineKeyboardButton("❌ Отмена", callback_data=f"admintask:{task_id}"),
                ]
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "deltask_confirm" and task_id:
        if db.delete_task(task_id):
            await safe_answer(query, "✅ Задание удалено!", show_alert=True)
        else:
            await safe_answer(query, "❌ Ошибка удаления.", show_alert=True)
        # Return to tasks list
        text = "📝 <b>Задания</b>\n\nНажми на задание для управления:\n\n"
        keyboard = []
        for topic in db.get_topics():
            tasks = db.get_tasks_by_topic(topic["topic_id"])
            if tasks:
                for t in tasks:
                    lang = t.get("language", "python")
                    emoji = "🐹" if lang == "go" else "🐍"
                    btn_text = f"{emoji} {t['task_id']}: {t['title'][:25]}"
                    keyboard.append(
                        [InlineKeyboardButton(btn_text, callback_data=f"admintask:{t['task_id']}")]
                    )
        if not keyboard:
            text += "<i>Пусто</i>\n"
        keyboard.append([InlineKeyboardButton("➕ Добавить задание", callback_data="create:task")])
        keyboard.append([InlineKeyboardButton("« Админ", callback_data="menu:admin")])
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )


async def cheater_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GOD MODE: Punish cheater - mark as failed and remove points."""
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await safe_answer(query, "⛔")
        return

    parts = query.data.split(":")
    sub_id = int(parts[1])
    penalty = int(parts[2]) if len(parts) > 2 else 0

    sub = db.get_submission_by_id(sub_id)
    if not sub:
        await safe_answer(query, "Не найден.")
        return

    if db.punish_cheater(sub_id, penalty):
        student = db.get_student_by_id(sub["student_id"])
        penalty_text = f" и -{penalty}⭐" if penalty > 0 else ""
        await safe_answer(query, f"🚨 Списывание отмечено{penalty_text}!", show_alert=True)

        # Notify student about punishment
        if student:
            task = db.get_task(sub["task_id"])
            task_name = task["title"] if task else sub["task_id"]
            await notify_student(
                context,
                student["user_id"],
                f"🚨 <b>Обнаружено списывание!</b>\n\n"
                f"Задание: <b>{escape_html(task_name)}</b>\n"
                f"Решение аннулировано" + (f", штраф: -{penalty}⭐" if penalty > 0 else ""),
            )
    else:
        await safe_answer(query, "Ошибка.", show_alert=True)

    await code_callback(update, context)


async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    sub_id = int(query.data.split(":")[1])
    # Clear any pending "creating" state to avoid conflicts
    context.user_data.pop("creating", None)
    context.user_data["feedback_for"] = sub_id
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Отмена", callback_data=f"code:{sub_id}")]]
    )
    await query.edit_message_text(
        f"💬 Отправь фидбек для попытки #{sub_id}:", reply_markup=keyboard
    )


async def delsub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await safe_answer(query, "⛔")
        return
    sub_id = int(query.data.split(":")[1])
    sub = db.get_submission_by_id(sub_id)
    if sub and db.delete_submission(sub_id):
        await safe_answer(query, "Удалено!", show_alert=True)
        await recent_callback(update, context)
    else:
        await safe_answer(query, "Ошибка.", show_alert=True)


async def assign_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    parts = query.data.split(":")
    student_id = int(parts[1])
    student = db.get_student_by_id(student_id)
    if not student:
        await query.edit_message_text("Не найден.")
        return
    context.user_data["assigning_to"] = student_id
    modules = db.get_modules()
    keyboard = [
        [InlineKeyboardButton(f"📦 {m['name']}", callback_data=f"assignmod:{m['module_id']}")]
        for m in modules
    ]
    assigned = db.get_assigned_tasks(student_id)
    if assigned:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📌 Назначенные ({len(assigned)})", callback_data=f"assigned:{student_id}"
                )
            ]
        )
    keyboard.append(
        [InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")]
    )
    name = escape_html(student.get("first_name") or "?")
    await query.edit_message_text(
        f"📌 Назначить задание для <b>{name}</b>\n\nВыбери модуль:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def assignmod_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    module_id = query.data.split(":")[1]
    student_id = context.user_data.get("assigning_to")
    if not student_id:
        await query.edit_message_text("Ошибка.")
        return
    topics = db.get_topics_by_module(module_id)
    keyboard = [
        [InlineKeyboardButton(f"📚 {t['name']}", callback_data=f"assigntopic:{t['topic_id']}")]
        for t in topics
    ]
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"assign:{student_id}")])
    await query.edit_message_text("Выбери тему:", reply_markup=InlineKeyboardMarkup(keyboard))


async def assigntopic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    topic_id = query.data.split(":")[1]
    student_id = context.user_data.get("assigning_to")
    if not student_id:
        await query.edit_message_text("Ошибка.")
        return
    tasks = db.get_tasks_by_topic(topic_id)
    keyboard = []
    for t in tasks:
        is_assigned = db.is_task_assigned(student_id, t["task_id"])
        prefix = "✅ " if is_assigned else ""
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{prefix}{t['task_id']}: {t['title']}",
                    callback_data=f"toggleassign:{t['task_id']}",
                )
            ]
        )
    topic = db.get_topic(topic_id)
    keyboard.append(
        [
            InlineKeyboardButton(
                "« Назад",
                callback_data=(
                    f"assignmod:{topic['module_id']}" if topic else f"assign:{student_id}"
                ),
            )
        ]
    )
    await query.edit_message_text(
        "Выбери задание (✅ = уже назначено):", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def toggleassign_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await safe_answer(query, "⛔")
        return
    task_id = query.data.split(":")[1]
    student_id = context.user_data.get("assigning_to")
    if not student_id:
        await safe_answer(query, "Ошибка.")
        return
    if db.is_task_assigned(student_id, task_id):
        db.unassign_task(student_id, task_id)
        await safe_answer(query, "Снято!")
    else:
        db.assign_task(student_id, task_id)
        await safe_answer(query, "Назначено!")
        # Notify student about new assignment with direct button
        student = db.get_student_by_id(student_id)
        task = db.get_task(task_id)
        if student and task:
            try:
                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📝 Открыть задание", callback_data=f"task:{task_id}")]]
                )
                await context.bot.send_message(
                    chat_id=student["user_id"],
                    text=f"📌 <b>Вам назначено новое задание!</b>\n\n"
                    f"<b>{escape_html(task['title'])}</b>\n"
                    f"ID: <code>{task_id}</code>",
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            except Exception as e:
                print(f"Failed to notify student {student['user_id']}: {e}")
    task = db.get_task(task_id)
    if task:
        await assigntopic_callback(update, context)


async def assigned_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    student_id = int(query.data.split(":")[1])
    student = db.get_student_by_id(student_id)
    assigned = db.get_assigned_tasks(student_id)
    name = escape_html(student.get("first_name") or "?") if student else "?"
    text = f"📌 Назначенные задания для <b>{name}</b>:\n\n"
    keyboard = []
    for t in assigned:
        solved = db.has_solved(student_id, t["task_id"])
        status = "✅" if solved else "⬜"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{status} {t['task_id']}: {t['title']}",
                    callback_data=f"unassign:{student_id}:{t['task_id']}",
                )
            ]
        )
    if not assigned:
        text += "<i>Пусто</i>"
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"assign:{student_id}")])
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def unassign_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await safe_answer(query, "⛔")
        return
    parts = query.data.split(":")
    student_id = int(parts[1])
    task_id = parts[2]
    db.unassign_task(student_id, task_id)
    await safe_answer(query, "Снято!")
    context.user_data["assigning_to"] = student_id
    await assigned_callback(update, context)


async def editname_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin edits student name."""
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return

    student_id = int(query.data.split(":")[1])
    student = db.get_student_by_id(student_id)
    if not student:
        await query.edit_message_text("Не найден.")
        return

    context.user_data["editing_student_name"] = student_id
    name = escape_html(student.get("first_name") or "?")
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Отмена", callback_data=f"student:{student['user_id']}")]]
    )
    await query.edit_message_text(
        f"✏️ <b>Редактирование имени</b>\n\n"
        f"Текущее имя: <b>{name}</b>\n\n"
        f"Отправь новое имя для студента:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def show_mentors_view(query, student_id: int):
    """Helper to render mentors view."""
    student = db.get_student_by_id(student_id)
    if not student:
        await query.edit_message_text("Не найден.")
        return

    name = escape_html(student.get("first_name") or student.get("username") or "?")
    mentors = db.get_student_mentors(student_id)
    admins = db.get_all_admins()

    # Create lookup for admin names
    admin_names = {a["user_id"]: a.get("name") or f"ID:{a['user_id']}" for a in admins}

    text = f"👨‍🏫 <b>Менторы студента {name}</b>\n\n"

    if mentors:
        text += "<b>Назначенные менторы:</b>\n"
        for m in mentors:
            mentor_name = admin_names.get(m["mentor_user_id"], f"ID:{m['mentor_user_id']}")
            text += f"• {escape_html(mentor_name)}\n"
    else:
        text += "<i>Менторы не назначены</i>\n"

    text += "\n<b>Выбери ментора:</b>"

    keyboard = []
    for admin in admins:
        is_mentor = any(m["mentor_user_id"] == admin["user_id"] for m in mentors)
        emoji = "✅" if is_mentor else "➕"
        action = "unmentor" if is_mentor else "addmentor"
        admin_display = admin.get("name") or f"ID:{admin['user_id']}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{emoji} {admin_display}",
                    callback_data=f"{action}:{student_id}:{admin['user_id']}",
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton("« Назад", callback_data=f"student:{student['user_id']}")]
    )

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def mentors_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage mentors for a student."""
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return

    student_id = int(query.data.split(":")[1])
    await show_mentors_view(query, student_id)


async def addmentor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add mentor to student."""
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return

    parts = query.data.split(":")
    student_id = int(parts[1])
    mentor_user_id = int(parts[2])

    if db.assign_mentor(student_id, mentor_user_id):
        await safe_answer(query, "✅ Ментор назначен!", show_alert=True)
    else:
        await safe_answer(query, "Уже назначен", show_alert=True)

    await show_mentors_view(query, student_id)


async def unmentor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove mentor from student."""
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return

    parts = query.data.split(":")
    student_id = int(parts[1])
    mentor_user_id = int(parts[2])

    if db.unassign_mentor(student_id, mentor_user_id):
        await safe_answer(query, "❌ Ментор удалён", show_alert=True)

    await show_mentors_view(query, student_id)


async def hired_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin marks student as hired."""
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return

    student_id = int(query.data.split(":")[1])
    student = db.get_student_by_id(student_id)
    if not student:
        await query.edit_message_text("Не найден.")
        return

    name = escape_html(student.get("first_name") or "?")
    stats = db.get_student_stats(student_id)

    text = (
        f"🎉 <b>Архивировать студента</b>\n\n"
        f"Студент: <b>{name}</b>\n"
        f"Решено: {stats['solved_tasks']}/{stats['total_tasks']}\n"
        f"Бонусы: {stats['bonus_points']}⭐\n\n"
        f"Выберите причину:"
    )

    keyboard = [
        [InlineKeyboardButton("🎉 Устроен на работу", callback_data=f"archive:{student_id}:HIRED")],
        [
            InlineKeyboardButton(
                "📚 Завершил обучение", callback_data=f"archive:{student_id}:GRADUATED"
            )
        ],
        [InlineKeyboardButton("🚫 Отчислен", callback_data=f"archive:{student_id}:EXPELLED")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"student:{student['user_id']}")],
    ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin archives student with reason, asks for feedback."""
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return

    parts = query.data.split(":")
    student_id = int(parts[1])
    reason = parts[2]

    student = db.get_student_by_id(student_id)
    if not student:
        await query.edit_message_text("Не найден.")
        return

    context.user_data["archiving_student"] = student_id
    context.user_data["archive_reason"] = reason

    name = escape_html(student.get("first_name") or "?")
    reason_text = {
        "HIRED": "🎉 Устроен на работу",
        "GRADUATED": "📚 Завершил обучение",
        "EXPELLED": "🚫 Отчислен",
    }.get(reason, reason)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⏭ Пропустить", callback_data=f"skip_feedback:{student_id}:{reason}"
                )
            ],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"student:{student['user_id']}")],
        ]
    )

    await query.edit_message_text(
        f"📝 <b>Обратная связь</b>\n\n"
        f"Студент: <b>{name}</b>\n"
        f"Статус: {reason_text}\n\n"
        f"Напишите отзыв о студенте "
        f"(куда устроился, как прошло обучение, комментарии):",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def skip_feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Archive without feedback."""
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return

    parts = query.data.split(":")
    student_id = int(parts[1])
    reason = parts[2]

    db.archive_student(student_id, reason, "")
    context.user_data.pop("archiving_student", None)
    context.user_data.pop("archive_reason", None)

    await query.edit_message_text("✅ Студент архивирован!", reply_markup=back_to_admin_keyboard())


async def archived_student_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View archived student details."""
    query = update.callback_query
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return

    user_id = int(query.data.split(":")[1])
    student = db.get_student(user_id)
    if not student:
        await query.edit_message_text("Не найден.")
        return

    name = escape_html(student.get("first_name") or "?")
    username = f"@{student.get('username')}" if student.get("username") else "нет username"
    stats = db.get_student_stats(student["id"])

    reason = student.get("archive_reason", "?")
    reason_text = {
        "HIRED": "🎉 Устроен на работу",
        "GRADUATED": "📚 Завершил обучение",
        "EXPELLED": "🚫 Отчислен",
    }.get(reason, reason)

    archived_at = student.get("archived_at", "?")[:10] if student.get("archived_at") else "?"

    text = (
        f"🎓 <b>{name}</b>\n"
        f"👤 {username}\n"
        f"ID: <code>{user_id}</code>\n\n"
        f"📊 Итоги:\n"
        f"✅ Решено: {stats['solved_tasks']}/{stats['total_tasks']}\n"
        f"⭐ Бонусов: {stats['bonus_points']}\n\n"
        f"📋 Статус: {reason_text}\n"
        f"📅 Дата: {archived_at}"
    )

    if student.get("archive_feedback"):
        text += f"\n\n💬 <b>Отзыв:</b>\n{escape_html(student['archive_feedback'])}"

    keyboard = [
        [InlineKeyboardButton("🔄 Восстановить", callback_data=f"restore:{student['id']}")],
        [InlineKeyboardButton("« Выпускники", callback_data="admin:archived")],
    ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restore archived student."""
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await safe_answer(query, "⛔")
        return

    student_id = int(query.data.split(":")[1])

    # Clear archive fields
    with db.get_db() as conn:
        conn.execute(
            "UPDATE students SET archived_at = NULL, archive_reason = NULL, archive_feedback = NULL WHERE id = ?",
            (student_id,),
        )

    await safe_answer(query, "✅ Студент восстановлен!", show_alert=True)
    await query.edit_message_text(
        "✅ Студент восстановлен и снова активен.", reply_markup=back_to_admin_keyboard()
    )


@require_admin
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    modules = db.get_modules()
    topics = db.get_topics()
    tasks = db.get_all_tasks()
    text = (
        f"👑 <b>Админ</b>\n\n📦 Модулей: {len(modules)}\n"
        f"📚 Тем: {len(topics)}\n📝 Заданий: {len(tasks)}"
    )
    await update.message.reply_text(
        text, reply_markup=admin_menu_keyboard(update.effective_user.id), parse_mode="HTML"
    )


@require_admin
async def gen_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = int(context.args[0]) if context.args else 5
    count = max(1, min(50, count))
    codes = db.create_codes(count)
    text = "🎫 <b>Коды</b>\n\n" + "\n".join(f"<code>{c}</code>" for c in codes)
    await update.message.reply_text(text, parse_mode="HTML")


@require_admin
async def del_task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("<code>/deltask task_id</code>", parse_mode="HTML")
        return
    await update.message.reply_text(
        "✅ Удалено." if db.delete_task(context.args[0]) else "❌ Не найдено."
    )


@require_admin
async def del_module_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("<code>/delmodule module_id</code>", parse_mode="HTML")
        return
    await update.message.reply_text(
        "✅ Удалено." if db.delete_module(context.args[0]) else "❌ Не найден или есть темы."
    )


@require_admin
async def del_topic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("<code>/deltopic topic_id</code>", parse_mode="HTML")
        return
    result = db.delete_topic(context.args[0])
    msg = "✅ Удалено." if result else "❌ Не найдена или есть задания."
    await update.message.reply_text(msg)
