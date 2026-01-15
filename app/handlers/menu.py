"""Menu navigation handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from app.utils import escape_html, safe_answer, safe_edit
from app.keyboards import main_menu_keyboard, admin_menu_keyboard, back_to_menu_keyboard


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu:* callbacks."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    is_admin = db.is_admin(user.id)
    action = query.data.split(":")[1]

    if action == "main":
        has_assigned = False
        can_spin = False
        unread_ann = 0
        student = db.get_student(user.id)
        if student:
            has_assigned = len(db.get_assigned_tasks(student["id"])) > 0
            can_spin = db.can_spin_daily(student["id"])
            unread_ann = db.get_unread_announcements_count(student["id"])
        await safe_edit(
            query,
            "🏠 <b>Главное меню</b>",
            reply_markup=main_menu_keyboard(is_admin, has_assigned, can_spin, unread_ann),
        )
    elif action == "mystats":
        student = db.get_student(user.id)
        if not student:
            await query.edit_message_text(
                "Не зарегистрирован.", reply_markup=back_to_menu_keyboard()
            )
            return
        stats = db.get_student_stats(student["id"])
        text = (
            f"📊 <b>Моя статистика</b>\n\n"
            f"✅ Решено: <b>{stats['solved_tasks']}</b>/{stats['total_tasks']}\n"
            f"⭐ Бонусы: <b>{stats['bonus_points']}</b>\n"
            f"🎖 Аппрувов: <b>{stats['approved_count']}</b>\n"
            f"📤 Отправок: <b>{stats['total_submissions']}</b>"
        )
        keyboard = [
            [InlineKeyboardButton("📋 Мои попытки", callback_data="myattempts:0")],
            [InlineKeyboardButton("« Главное меню", callback_data="menu:main")],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )
    elif action == "leaderboard":
        leaders = db.get_leaderboard(15)
        if not leaders:
            await query.edit_message_text("Пока пусто.", reply_markup=back_to_menu_keyboard())
            return
        text = "🏆 <b>Лидерборд</b>\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for l in leaders:
            name = escape_html(l.get("first_name") or l.get("username") or "???")
            medal = medals[l["rank"] - 1] if l["rank"] <= 3 else f"{l['rank']}."
            text += f"{medal} <b>{name}</b> — {l['solved']} ✅"
            if l["bonus_points"] > 0:
                text += f" +{l['bonus_points']}⭐"
            text += f" = <b>{l['score']}</b>\n"
        keyboard = [
            [InlineKeyboardButton("💀 Доска позора", callback_data="menu:shameboard")],
            [InlineKeyboardButton("« Главное меню", callback_data="menu:main")],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )
    elif action == "shameboard":
        cheaters = db.get_cheaters_board()
        if not cheaters:
            text = "💀 <b>Доска позора</b>\n\n✨ Пока чисто! Все честные."
        else:
            text = "💀 <b>ДОСКА ПОЗОРА</b> 💀\n\n"
            text += "🚨 <i>Пойманы на списывании:</i>\n\n"
            shame_emoji = ["🤡", "🐀", "🦨", "💩", "🐍", "🦝", "🐛", "🪳"]
            for i, c in enumerate(cheaters):
                name = escape_html(c.get("first_name") or c.get("username") or "???")
                emoji = shame_emoji[i % len(shame_emoji)]
                count = c["cheat_count"]
                text += f"{emoji} <b>{name}</b> — {count} списываний\n"
            text += "\n<i>Не списывай — будь честен!</i>"
        keyboard = [
            [InlineKeyboardButton("🏆 Лидерборд", callback_data="menu:leaderboard")],
            [InlineKeyboardButton("« Главное меню", callback_data="menu:main")],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )
    elif action == "admin":
        if not is_admin:
            await query.edit_message_text("⛔")
            return
        modules = db.get_modules()
        topics = db.get_topics()
        tasks = db.get_all_tasks()
        students = db.get_all_students()
        text = (
            "👑 <b>Админ</b>\n\n"
            f"📦 Модулей: <b>{len(modules)}</b>\n"
            f"📚 Тем: <b>{len(topics)}</b>\n"
            f"📝 Заданий: <b>{len(tasks)}</b>\n"
            f"👥 Студентов: <b>{len(students)}</b>"
        )
        await query.edit_message_text(
            text, reply_markup=admin_menu_keyboard(user.id), parse_mode="HTML"
        )


async def modules_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle modules:list callback - show all modules."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    student = db.get_student(user.id)
    student_id = student["id"] if student else None
    modules = db.get_modules()
    
    if not modules:
        await query.edit_message_text("Нет модулей.", reply_markup=back_to_menu_keyboard())
        return
    
    keyboard = []
    for m in modules:
        topics = db.get_topics_by_module(m["module_id"])
        total = sum(len(db.get_tasks_by_topic(t["topic_id"])) for t in topics)
        solved = 0
        if student_id:
            for t in topics:
                for task in db.get_tasks_by_topic(t["topic_id"]):
                    if db.has_solved(student_id, task["task_id"]):
                        solved += 1
        lang_emoji = "🐹" if m.get("language") == "go" else "🐍"
        btn = f"{lang_emoji} {m['name']} ({solved}/{total})"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"module:{m['module_id']}")])
    keyboard.append([InlineKeyboardButton("« Меню", callback_data="menu:main")])
    await query.edit_message_text(
        "📚 <b>Модули</b>\n\n🐍 Python  🐹 Go",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def module_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle module:{id} callback - show topics in module."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    student = db.get_student(user.id)
    student_id = student["id"] if student else None
    module_id = query.data.split(":")[1]
    module = db.get_module(module_id)
    
    if not module:
        await query.edit_message_text("Не найден.")
        return
    
    topics = db.get_topics_by_module(module_id)
    keyboard = []
    for t in topics:
        tasks = db.get_tasks_by_topic(t["topic_id"])
        solved = sum(
            1 for task in tasks if student_id and db.has_solved(student_id, task["task_id"])
        )
        total = len(tasks)
        if total > 0:
            btn = f"📚 {t['name']} ({solved}/{total})"
            keyboard.append([InlineKeyboardButton(btn, callback_data=f"topic:{t['topic_id']}")])
    keyboard.append([InlineKeyboardButton("« Модули", callback_data="modules:list")])
    await query.edit_message_text(
        f"📦 <b>{escape_html(module['name'])}</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle topic:{id} callback - show tasks in topic."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    student = db.get_student(user.id)
    student_id = student["id"] if student else None
    topic_id = query.data.split(":")[1]
    topic = db.get_topic(topic_id)
    
    if not topic:
        await query.edit_message_text("Не найден.")
        return
    
    tasks = db.get_tasks_by_topic(topic_id)
    keyboard = []
    for task in tasks:
        status = "✅" if student_id and db.has_solved(student_id, task["task_id"]) else "⬜"
        btn = f"{status} {task['task_id']}: {task['title']}"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"task:{task['task_id']}")])
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"module:{topic['module_id']}")])
    await query.edit_message_text(
        f"📚 <b>{escape_html(topic['name'])}</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
