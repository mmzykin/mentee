import os
import sys
import re
import tempfile
import subprocess
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import database as db

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
EXEC_TIMEOUT = 10
ADMIN_USERNAMES = ["qwerty1492"]
BONUS_POINTS_PER_APPROVAL = 1


def main_menu_keyboard(is_admin=False):
    keyboard = [
        [InlineKeyboardButton("📚 Задания", callback_data="modules:list")],
        [InlineKeyboardButton("🏆 Лидерборд", callback_data="menu:leaderboard")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="menu:mystats")],
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="menu:admin")])
    return InlineKeyboardMarkup(keyboard)


def admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Модули", callback_data="admin:modules"),
            InlineKeyboardButton("📚 Темы", callback_data="admin:topics"),
        ],
        [
            InlineKeyboardButton("📝 Задания", callback_data="admin:tasks"),
            InlineKeyboardButton("👥 Студенты", callback_data="admin:students"),
        ],
        [
            InlineKeyboardButton("🎫 Коды", callback_data="admin:codes"),
            InlineKeyboardButton("🧹 Очистка", callback_data="admin:cleanup"),
        ],
        [InlineKeyboardButton("« Главное меню", callback_data="menu:main")],
    ])


def back_to_menu_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Главное меню", callback_data="menu:main")]])


def back_to_admin_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Админ-панель", callback_data="menu:admin")]])


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def parse_task_format(text: str) -> Optional[dict]:
    try:
        topic_match = re.search(r"TOPIC:\s*(\S+)", text)
        task_id_match = re.search(r"TASK_ID:\s*(\S+)", text)
        title_match = re.search(r"TITLE:\s*(.+?)(?:\n|---)", text)
        if not all([topic_match, task_id_match, title_match]):
            return None
        desc_match = re.search(r"---DESCRIPTION---\s*\n(.*?)---TESTS---", text, re.DOTALL)
        tests_match = re.search(r"---TESTS---\s*\n(.+)", text, re.DOTALL)
        if not desc_match or not tests_match:
            return None
        return {
            "topic_id": topic_match.group(1).strip(),
            "task_id": task_id_match.group(1).strip(),
            "title": title_match.group(1).strip(),
            "description": desc_match.group(1).strip(),
            "test_code": tests_match.group(1).strip(),
        }
    except:
        return None


def run_code_with_tests(code: str, test_code: str) -> tuple[bool, str]:
    full_code = code + "\n\n" + test_code
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(full_code)
        temp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True, text=True, timeout=EXEC_TIMEOUT,
            cwd=tempfile.gettempdir(),
        )
        output = result.stdout + result.stderr
        passed = result.returncode == 0 and "✅" in output
        return passed, output.strip()
    except subprocess.TimeoutExpired:
        return False, f"⏰ Timeout: {EXEC_TIMEOUT} сек"
    except Exception as e:
        return False, f"❌ Ошибка: {e}"
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass


def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not db.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Только для админов.")
            return
        return await func(update, context)
    return wrapper


def require_registered(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if db.is_admin(user_id) or db.is_registered(user_id):
            return await func(update, context)
        await update.message.reply_text("⛔ Сначала /register КОД")
        return
    return wrapper


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = escape_html(user.first_name)
    if user.username and user.username.lower() in ADMIN_USERNAMES:
        if not db.is_admin(user.id):
            db.add_admin(user.id)
            await update.message.reply_text(f"👑 <b>{name}</b>, ты теперь админ!", reply_markup=main_menu_keyboard(is_admin=True), parse_mode="HTML")
            return
    if db.get_admin_count() == 0:
        db.add_admin(user.id)
        await update.message.reply_text(f"👑 <b>{name}</b>, ты первый — теперь админ!", reply_markup=main_menu_keyboard(is_admin=True), parse_mode="HTML")
        return
    is_admin = db.is_admin(user.id)
    if is_admin:
        await update.message.reply_text(f"👑 <b>{name}</b>!", reply_markup=main_menu_keyboard(is_admin=True), parse_mode="HTML")
    elif db.get_student(user.id):
        await update.message.reply_text(f"👋 <b>{name}</b>!", reply_markup=main_menu_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(f"👋 <b>{name}</b>!\n\nРегистрация: /register КОД", parse_mode="HTML")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = db.is_admin(update.effective_user.id)
    text = "📖 <b>Команды</b>\n\n/start — меню\n/topics — задания\n/leaderboard — рейтинг"
    if is_admin:
        text += "\n\n👑 <b>Админ</b>\n/admin — панель\n/gencodes N — коды"
    await update.message.reply_text(text, reply_markup=main_menu_keyboard(is_admin), parse_mode="HTML")


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db.is_registered(user.id):
        await update.message.reply_text("✅ Уже зарегистрирован!", reply_markup=main_menu_keyboard())
        return
    if not context.args:
        await update.message.reply_text("Используй: <code>/register КОД</code>", parse_mode="HTML")
        return
    if db.register_student(user.id, user.username or "", user.first_name or "", context.args[0]):
        await update.message.reply_text(f"✅ Добро пожаловать, <b>{escape_html(user.first_name)}</b>!", reply_markup=main_menu_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text("❌ Неверный код.")


async def notify_student(context: ContextTypes.DEFAULT_TYPE, student_user_id: int, message: str):
    """Send notification to student"""
    try:
        await context.bot.send_message(chat_id=student_user_id, text=message, parse_mode="HTML")
        return True
    except Exception as e:
        print(f"Failed to notify student {student_user_id}: {e}")
        return False


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    is_admin = db.is_admin(user.id)
    action = query.data.split(":")[1]
    
    if action == "main":
        await query.edit_message_text("🏠 <b>Главное меню</b>", reply_markup=main_menu_keyboard(is_admin), parse_mode="HTML")
    elif action == "mystats":
        student = db.get_student(user.id)
        if not student:
            await query.edit_message_text("Не зарегистрирован.", reply_markup=back_to_menu_keyboard())
            return
        stats = db.get_student_stats(student["id"])
        assigned = db.get_assigned_tasks(student["id"])
        text = (
            f"📊 <b>Моя статистика</b>\n\n"
            f"✅ Решено: <b>{stats['solved_tasks']}</b>/{stats['total_tasks']}\n"
            f"⭐ Бонусы: <b>{stats['bonus_points']}</b>\n"
            f"🎖 Аппрувов: <b>{stats['approved_count']}</b>\n"
            f"📤 Отправок: <b>{stats['total_submissions']}</b>"
        )
        if assigned:
            text += f"\n📌 Назначено: <b>{len(assigned)}</b>"
        keyboard = [
            [InlineKeyboardButton("📋 Мои попытки", callback_data="myattempts:0")],
            [InlineKeyboardButton("📌 Назначенные мне", callback_data="myassigned:0")],
            [InlineKeyboardButton("« Главное меню", callback_data="menu:main")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif action == "leaderboard":
        leaders = db.get_leaderboard(15)
        if not leaders:
            await query.edit_message_text("Пока пусто.", reply_markup=back_to_menu_keyboard())
            return
        text = "🏆 <b>Лидерборд</b>\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for l in leaders:
            name = escape_html(l.get("first_name") or l.get("username") or "???")
            medal = medals[l["rank"]-1] if l["rank"] <= 3 else f"{l['rank']}."
            text += f"{medal} <b>{name}</b> — {l['solved']} ✅"
            if l["bonus_points"] > 0:
                text += f" +{l['bonus_points']}⭐"
            text += f" = <b>{l['score']}</b>\n"
        await query.edit_message_text(text, reply_markup=back_to_menu_keyboard(), parse_mode="HTML")
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
        await query.edit_message_text(text, reply_markup=admin_menu_keyboard(), parse_mode="HTML")


async def modules_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
        btn = f"📦 {m['name']} ({solved}/{total})"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"module:{m['module_id']}")])
    keyboard.append([InlineKeyboardButton("« Меню", callback_data="menu:main")])
    await query.edit_message_text("📦 <b>Модули</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def module_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
        solved = sum(1 for task in tasks if student_id and db.has_solved(student_id, task["task_id"]))
        total = len(tasks)
        if total > 0:
            btn = f"📚 {t['name']} ({solved}/{total})"
            keyboard.append([InlineKeyboardButton(btn, callback_data=f"topic:{t['topic_id']}")])
    keyboard.append([InlineKeyboardButton("« Модули", callback_data="modules:list")])
    await query.edit_message_text(f"📦 <b>{escape_html(module['name'])}</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
    await query.edit_message_text(f"📚 <b>{escape_html(topic['name'])}</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = query.data.split(":")[1]
    task = db.get_task(task_id)
    if not task:
        await query.edit_message_text("Не найден.")
        return
    desc = task["description"][:3500]
    text = f"📝 <b>{escape_html(task['title'])}</b>\nID: <code>{task_id}</code>\n\n{desc}"
    topic = db.get_topic(task["topic_id"])
    back_target = f"topic:{task['topic_id']}" if topic else "modules:list"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Отправить", callback_data=f"submit:{task_id}")],
        [InlineKeyboardButton("« Назад", callback_data=back_target)]
    ])
    await query.edit_message_text(text, reply_markup=keyboard)


async def submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data=f"task:{task_id}")]])
    await query.edit_message_text(f"📤 <b>{escape_html(task['title'])}</b>\n\nОтправь код:", reply_markup=keyboard, parse_mode="HTML")


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    action = query.data.split(":")[1]
    
    if action == "modules":
        modules = db.get_modules()
        text = "📦 <b>Модули</b>\n\n"
        if modules:
            for m in modules:
                topics_count = len(db.get_topics_by_module(m["module_id"]))
                text += f"• <code>{m['module_id']}</code>: {escape_html(m['name'])} ({topics_count} тем)\n"
        else:
            text += "<i>Пусто</i>\n"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить модуль", callback_data="create:module")],
            [InlineKeyboardButton("« Админ", callback_data="menu:admin")]
        ])
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
                    text += f"  • <code>{t['topic_id']}</code>: {escape_html(t['name'])} ({count})\n"
            else:
                text += "  <i>(пусто)</i>\n"
            text += "\n"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить тему", callback_data="create:topic_select")],
            [InlineKeyboardButton("« Админ", callback_data="menu:admin")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    
    elif action == "tasks":
        text = "📝 <b>Задания</b>\n\n"
        has_tasks = False
        for topic in db.get_topics():
            tasks = db.get_tasks_by_topic(topic["topic_id"])
            if tasks:
                has_tasks = True
                text += f"<b>{escape_html(topic['name'])}</b>\n"
                for t in tasks:
                    text += f"  • <code>{t['task_id']}</code>: {escape_html(t['title'])}\n"
                text += "\n"
        if not has_tasks:
            text += "<i>Пусто</i>\n"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить задание", callback_data="create:task")],
            [InlineKeyboardButton("« Админ", callback_data="menu:admin")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    
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
            keyboard.append([InlineKeyboardButton(f"🎓 Выпускники ({len(archived)})", callback_data="admin:archived")])
        keyboard.append([InlineKeyboardButton("« Админ", callback_data="menu:admin")])
        text = f"👥 <b>Активные студенты</b> ({len(students)})"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
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
            keyboard.append([InlineKeyboardButton(btn, callback_data=f"archived_student:{s['user_id']}")])
        keyboard.append([InlineKeyboardButton("« Студенты", callback_data="admin:students")])
        await query.edit_message_text("🎓 <b>Выпускники</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
    elif action == "codes":
        codes = db.get_unused_codes()
        text = f"🎫 <b>Коды</b> ({len(codes)})\n\n" if codes else "<i>Нет кодов.</i>"
        for c in codes[:20]:
            text += f"<code>{c['code']}</code>\n"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Создать 5", callback_data="admin:gencodes")],
            [InlineKeyboardButton("« Админ", callback_data="menu:admin")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    
    elif action == "gencodes":
        codes = db.create_codes(5)
        text = "🎫 <b>Созданы</b>\n\n" + "\n".join(f"<code>{c}</code>" for c in codes)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Ещё 5", callback_data="admin:gencodes")],
            [InlineKeyboardButton("« Админ", callback_data="menu:admin")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    
    elif action == "cleanup":
        deleted = db.cleanup_old_code()
        await query.edit_message_text(f"🧹 Удалено кода из <b>{deleted}</b> отправок.", reply_markup=back_to_admin_keyboard(), parse_mode="HTML")


async def create_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    
    if action == "module":
        context.user_data["creating"] = "module"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin:modules")]])
        await query.edit_message_text("📦 <b>Новый модуль</b>\n\nОтправь ID и название:\n<code>2 ООП</code>", reply_markup=keyboard, parse_mode="HTML")
    
    elif action == "topic_select":
        modules = db.get_modules()
        if not modules:
            await query.edit_message_text("Сначала создай модуль.", reply_markup=back_to_admin_keyboard())
            return
        keyboard = [[InlineKeyboardButton(f"📦 {m['name']}", callback_data=f"create:topic:{m['module_id']}")] for m in modules]
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="admin:topics")])
        await query.edit_message_text("Выбери модуль для темы:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif action == "topic" and len(parts) > 2:
        module_id = parts[2]
        module = db.get_module(module_id)
        if not module:
            await query.edit_message_text("Модуль не найден.")
            return
        context.user_data["creating"] = "topic"
        context.user_data["module_id"] = module_id
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin:topics")]])
        await query.edit_message_text(f"📚 <b>Новая тема в {escape_html(module['name'])}</b>\n\nОтправь ID и название:\n<code>2.1 Классы</code>", reply_markup=keyboard, parse_mode="HTML")
    
    elif action == "task":
        topics = db.get_topics()
        if not topics:
            await query.edit_message_text("Сначала создай тему.", reply_markup=back_to_admin_keyboard())
            return
        context.user_data["creating"] = "task"
        text = "📝 <b>Новое задание</b>\n\nТемы:\n"
        for t in topics:
            text += f"• <code>{t['topic_id']}</code>: {escape_html(t['name'])}\n"
        text += "\nОтправь в формате:\n<code>TOPIC: topic_id\nTASK_ID: task_id\nTITLE: Название\n---DESCRIPTION---\nОписание\n---TESTS---\ndef test(): ...</code>"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin:tasks")]])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


async def student_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
    text = (
        f"📋 <b>{name}</b>\n"
        f"👤 {username}\n"
        f"ID: <code>{user_id}</code>\n\n"
        f"✅ {stats['solved_tasks']}/{stats['total_tasks']}\n"
        f"⭐ Бонусов: {stats['bonus_points']}\n"
        f"📌 Назначено: {len(assigned)}"
    )
    keyboard = [
        [InlineKeyboardButton("📋 Последние 10 попыток", callback_data=f"recent:{student['id']}")],
        [InlineKeyboardButton("📝 По заданиям", callback_data=f"bytask:{student['id']}")],
        [InlineKeyboardButton("📌 Назначить задание", callback_data=f"assign:{student['id']}")],
        [
            InlineKeyboardButton("✏️ Изменить имя", callback_data=f"editname:{student['id']}"),
        ],
        [InlineKeyboardButton("🎉 Устроен на работу", callback_data=f"hired:{student['id']}")],
        [InlineKeyboardButton("« Студенты", callback_data="admin:students")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def recent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
        date = sub["submitted_at"][5:16].replace("T", " ") if sub["submitted_at"] else ""
        btn = f"{status}{approved}{feedback} #{sub['id']} {sub['task_id']} {date}"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"code:{sub['id']}")])
    keyboard.append([InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def bytask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
                keyboard.append([InlineKeyboardButton(btn, callback_data=f"attempts:{student_id}:{task['task_id']}")])
    if not keyboard:
        text += "<i>Нет попыток</i>"
    keyboard.append([InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def attempts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
        date = sub["submitted_at"][5:16].replace("T", " ") if sub["submitted_at"] else ""
        btn = f"{status}{approved}{feedback} #{sub['id']} {date}"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"code:{sub['id']}")])
    keyboard.append([InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    sub_id = int(query.data.split(":")[1])
    sub = db.get_submission_by_id(sub_id)
    if not sub:
        await query.edit_message_text("Не найден.")
        return
    status = "✅" if sub["passed"] else "❌"
    approved = " ⭐Аппрувнуто" if sub.get("approved") else ""
    code = sub["code"] or "[удалён]"
    if len(code) > 2500:
        code = code[:2500] + "\n...(обрезано)"
    text = f"<b>{status}{approved}</b>\nID: <code>#{sub['id']}</code>\nЗадание: <code>{sub['task_id']}</code>\nВремя: {sub['submitted_at'][:16]}\n\n<pre>{escape_html(code)}</pre>"
    if sub.get("feedback"):
        text += f"\n\n💬 <b>Фидбек:</b>\n{escape_html(sub['feedback'])}"
    keyboard = []
    row1 = []
    if sub["passed"] and not sub.get("approved"):
        row1.append(InlineKeyboardButton("⭐ Аппрув", callback_data=f"approve:{sub_id}"))
    elif sub.get("approved"):
        row1.append(InlineKeyboardButton("❌ Убрать аппрув", callback_data=f"unapprove:{sub_id}"))
    row1.append(InlineKeyboardButton("💬 Фидбек", callback_data=f"feedback:{sub_id}"))
    keyboard.append(row1)
    keyboard.append([InlineKeyboardButton("🗑 Удалить", callback_data=f"delsub:{sub_id}")])
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"recent:{sub['student_id']}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await query.answer("⛔")
        return
    sub_id = int(query.data.split(":")[1])
    sub = db.get_submission_by_id(sub_id)
    if db.approve_submission(sub_id, BONUS_POINTS_PER_APPROVAL):
        await query.answer("⭐ Аппрувнуто!", show_alert=True)
        # Notify student
        if sub:
            student = db.get_student_by_id(sub["student_id"])
            if student:
                task = db.get_task(sub["task_id"])
                task_name = task["title"] if task else sub["task_id"]
                await notify_student(
                    context, student["user_id"],
                    f"⭐ <b>Ваше решение аппрувнуто!</b>\n\n"
                    f"Задание: <b>{escape_html(task_name)}</b>\n"
                    f"Вы получили +{BONUS_POINTS_PER_APPROVAL} бонус!"
                )
    else:
        await query.answer("Уже или ошибка.", show_alert=True)
    await code_callback(update, context)


async def unapprove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await query.answer("⛔")
        return
    sub_id = int(query.data.split(":")[1])
    db.unapprove_submission(sub_id)
    await query.answer("Отменено.", show_alert=True)
    await code_callback(update, context)


async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    sub_id = int(query.data.split(":")[1])
    context.user_data["feedback_for"] = sub_id
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data=f"code:{sub_id}")]])
    await query.edit_message_text(f"💬 Отправь фидбек для попытки #{sub_id}:", reply_markup=keyboard)


async def delsub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await query.answer("⛔")
        return
    sub_id = int(query.data.split(":")[1])
    sub = db.get_submission_by_id(sub_id)
    if sub and db.delete_submission(sub_id):
        await query.answer("Удалено!", show_alert=True)
        await recent_callback(update, context)
    else:
        await query.answer("Ошибка.", show_alert=True)


async def assign_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
    keyboard = [[InlineKeyboardButton(f"📦 {m['name']}", callback_data=f"assignmod:{m['module_id']}")] for m in modules]
    assigned = db.get_assigned_tasks(student_id)
    if assigned:
        keyboard.append([InlineKeyboardButton(f"📌 Назначенные ({len(assigned)})", callback_data=f"assigned:{student_id}")])
    keyboard.append([InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")])
    name = escape_html(student.get("first_name") or "?")
    await query.edit_message_text(f"📌 Назначить задание для <b>{name}</b>\n\nВыбери модуль:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def assignmod_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    module_id = query.data.split(":")[1]
    student_id = context.user_data.get("assigning_to")
    if not student_id:
        await query.edit_message_text("Ошибка.")
        return
    student = db.get_student_by_id(student_id)
    topics = db.get_topics_by_module(module_id)
    keyboard = [[InlineKeyboardButton(f"📚 {t['name']}", callback_data=f"assigntopic:{t['topic_id']}")] for t in topics]
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"assign:{student_id}")])
    await query.edit_message_text("Выбери тему:", reply_markup=InlineKeyboardMarkup(keyboard))


async def assigntopic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
        keyboard.append([InlineKeyboardButton(f"{prefix}{t['task_id']}: {t['title']}", callback_data=f"toggleassign:{t['task_id']}")])
    topic = db.get_topic(topic_id)
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"assignmod:{topic['module_id']}" if topic else f"assign:{student_id}")])
    await query.edit_message_text("Выбери задание (✅ = уже назначено):", reply_markup=InlineKeyboardMarkup(keyboard))


async def toggleassign_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await query.answer("⛔")
        return
    task_id = query.data.split(":")[1]
    student_id = context.user_data.get("assigning_to")
    if not student_id:
        await query.answer("Ошибка.")
        return
    if db.is_task_assigned(student_id, task_id):
        db.unassign_task(student_id, task_id)
        await query.answer("Снято!")
    else:
        db.assign_task(student_id, task_id)
        await query.answer("Назначено!")
        # Notify student about new assignment
        student = db.get_student_by_id(student_id)
        task = db.get_task(task_id)
        if student and task:
            await notify_student(
                context, student["user_id"],
                f"📌 <b>Вам назначено новое задание!</b>\n\n"
                f"<b>{escape_html(task['title'])}</b>\n"
                f"ID: <code>{task_id}</code>\n\n"
                f"Откройте 📚 Задания для просмотра."
            )
    task = db.get_task(task_id)
    if task:
        await assigntopic_callback(update, context)


async def assigned_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
        keyboard.append([InlineKeyboardButton(f"{status} {t['task_id']}: {t['title']}", callback_data=f"unassign:{student_id}:{t['task_id']}")])
    if not assigned:
        text += "<i>Пусто</i>"
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"assign:{student_id}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def unassign_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await query.answer("⛔")
        return
    parts = query.data.split(":")
    student_id = int(parts[1])
    task_id = parts[2]
    db.unassign_task(student_id, task_id)
    await query.answer("Снято!")
    context.user_data["assigning_to"] = student_id
    await assigned_callback(update, context)


async def myattempts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Student's own attempts"""
    query = update.callback_query
    await query.answer()
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
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return
    
    text = f"📋 <b>Мои попытки</b> ({total} всего)\n\n"
    keyboard = []
    for sub in page_subs:
        status = "✅" if sub["passed"] else "❌"
        approved = "⭐" if sub.get("approved") else ""
        feedback = "💬" if sub.get("feedback") else ""
        date = sub["submitted_at"][5:16].replace("T", " ") if sub["submitted_at"] else ""
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
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def mycode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Student views their own submission"""
    query = update.callback_query
    await query.answer()
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
        f"Время: {sub['submitted_at'][:16]}\n\n"
        f"<pre>{escape_html(code)}</pre>"
    )
    
    if sub.get("feedback"):
        text += f"\n\n💬 <b>Фидбек от ментора:</b>\n{escape_html(sub['feedback'])}"
    
    keyboard = [[InlineKeyboardButton("« Мои попытки", callback_data="myattempts:0")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def myassigned_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Student's assigned tasks"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    student = db.get_student(user.id)
    if not student:
        await query.edit_message_text("Не зарегистрирован.", reply_markup=back_to_menu_keyboard())
        return
    
    assigned = db.get_assigned_tasks(student["id"])
    
    if not assigned:
        text = "📌 <b>Назначенные мне задания</b>\n\n<i>Пока ничего не назначено</i>"
        keyboard = [[InlineKeyboardButton("« Назад", callback_data="menu:mystats")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return
    
    text = f"📌 <b>Назначенные мне задания</b> ({len(assigned)})\n\n"
    keyboard = []
    for t in assigned:
        solved = db.has_solved(student["id"], t["task_id"])
        status = "✅" if solved else "⬜"
        btn = f"{status} {t['title']}"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"task:{t['task_id']}")])
    
    keyboard.append([InlineKeyboardButton("« Назад", callback_data="menu:mystats")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def editname_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin edits student name"""
    query = update.callback_query
    await query.answer()
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
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data=f"student:{student['user_id']}")]])
    await query.edit_message_text(
        f"✏️ <b>Редактирование имени</b>\n\n"
        f"Текущее имя: <b>{name}</b>\n\n"
        f"Отправь новое имя для студента:",
        reply_markup=keyboard, parse_mode="HTML"
    )


async def hired_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin marks student as hired"""
    query = update.callback_query
    await query.answer()
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
        [InlineKeyboardButton("📚 Завершил обучение", callback_data=f"archive:{student_id}:GRADUATED")],
        [InlineKeyboardButton("🚫 Отчислен", callback_data=f"archive:{student_id}:EXPELLED")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"student:{student['user_id']}")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin archives student with reason, asks for feedback"""
    query = update.callback_query
    await query.answer()
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
        "EXPELLED": "🚫 Отчислен"
    }.get(reason, reason)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ Пропустить", callback_data=f"skip_feedback:{student_id}:{reason}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"student:{student['user_id']}")]
    ])
    
    await query.edit_message_text(
        f"📝 <b>Обратная связь</b>\n\n"
        f"Студент: <b>{name}</b>\n"
        f"Статус: {reason_text}\n\n"
        f"Напишите отзыв о студенте (куда устроился, как прошло обучение, комментарии):",
        reply_markup=keyboard, parse_mode="HTML"
    )


async def skip_feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Archive without feedback"""
    query = update.callback_query
    await query.answer()
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
    """View archived student details"""
    query = update.callback_query
    await query.answer()
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
        "EXPELLED": "🚫 Отчислен"
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
        [InlineKeyboardButton("« Выпускники", callback_data="admin:archived")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restore archived student"""
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await query.answer("⛔")
        return
    
    student_id = int(query.data.split(":")[1])
    
    # Clear archive fields
    with db.get_db() as conn:
        conn.execute(
            "UPDATE students SET archived_at = NULL, archive_reason = NULL, archive_feedback = NULL WHERE id = ?",
            (student_id,)
        )
    
    await query.answer("✅ Студент восстановлен!", show_alert=True)
    await query.edit_message_text("✅ Студент восстановлен и снова активен.", reply_markup=back_to_admin_keyboard())


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    
    if db.is_admin(user.id):
        if context.user_data.get("creating") == "module":
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await update.message.reply_text("Формат: <code>id Название</code>", parse_mode="HTML")
                return
            if db.add_module(parts[0], parts[1], len(db.get_modules()) + 1):
                del context.user_data["creating"]
                await update.message.reply_text(f"✅ Модуль создан!", reply_markup=back_to_admin_keyboard())
            else:
                await update.message.reply_text("❌ ID занят.")
            return
        
        if context.user_data.get("creating") == "topic":
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await update.message.reply_text("Формат: <code>id Название</code>", parse_mode="HTML")
                return
            module_id = context.user_data.get("module_id", "1")
            if db.add_topic(parts[0], parts[1], module_id, len(db.get_topics_by_module(module_id)) + 1):
                context.user_data.pop("creating", None)
                context.user_data.pop("module_id", None)
                await update.message.reply_text(f"✅ Тема создана!", reply_markup=back_to_admin_keyboard())
            else:
                await update.message.reply_text("❌ ID занят.")
            return
        
        if context.user_data.get("creating") == "task":
            parsed = parse_task_format(text)
            if not parsed:
                await update.message.reply_text("❌ Неверный формат.")
                return
            topic = db.get_topic(parsed["topic_id"])
            if not topic:
                await update.message.reply_text(f"❌ Тема не найдена.", parse_mode="HTML")
                return
            if db.add_task(parsed["task_id"], parsed["topic_id"], parsed["title"], parsed["description"], parsed["test_code"]):
                del context.user_data["creating"]
                await update.message.reply_text(f"✅ Задание создано!", reply_markup=back_to_admin_keyboard())
            else:
                await update.message.reply_text("❌ ID занят.")
            return
        
        if context.user_data.get("feedback_for"):
            sub_id = context.user_data["feedback_for"]
            db.set_feedback(sub_id, text)
            del context.user_data["feedback_for"]
            await update.message.reply_text(f"💬 Фидбек сохранён для #{sub_id}!", reply_markup=back_to_admin_keyboard())
            # Notify student about feedback
            sub = db.get_submission_by_id(sub_id)
            if sub:
                student = db.get_student_by_id(sub["student_id"])
                if student:
                    task = db.get_task(sub["task_id"])
                    task_name = task["title"] if task else sub["task_id"]
                    await notify_student(
                        context, student["user_id"],
                        f"💬 <b>Новый фидбек от ментора!</b>\n\n"
                        f"Задание: <b>{escape_html(task_name)}</b>\n\n"
                        f"{escape_html(text)}"
                    )
            return
        
        if context.user_data.get("editing_student_name"):
            student_id = context.user_data["editing_student_name"]
            db.update_student_name(student_id, text)
            del context.user_data["editing_student_name"]
            student = db.get_student_by_id(student_id)
            await update.message.reply_text(f"✅ Имя изменено на: {escape_html(text)}", reply_markup=back_to_admin_keyboard())
            return
        
        if context.user_data.get("archiving_student"):
            student_id = context.user_data["archiving_student"]
            reason = context.user_data.get("archive_reason", "HIRED")
            db.archive_student(student_id, reason, text)
            del context.user_data["archiving_student"]
            context.user_data.pop("archive_reason", None)
            await update.message.reply_text(f"✅ Студент архивирован!\n\n💬 Отзыв сохранён.", reply_markup=back_to_admin_keyboard())
            return
    
    task_id = context.user_data.get("pending_task")
    if task_id:
        await process_submission(update, context, text)


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    task = db.get_task(task_id)
    if not task:
        await update.message.reply_text("❌ Задание не найдено.")
        return
    checking = await update.message.reply_text("⏳ Проверяю...")
    passed, output = run_code_with_tests(code, task["test_code"])
    sub_id = 0
    if student["id"] != 0:
        sub_id = db.add_submission(student["id"], task_id, code, passed, output)
    safe_output = escape_html(output[:1500])
    if passed:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎉 К заданиям", callback_data="modules:list")],
            [InlineKeyboardButton("🏆 Лидерборд", callback_data="menu:leaderboard")]
        ])
        result = f"✅ <b>Решено!</b> (#{sub_id})\n\n<pre>{safe_output}</pre>"
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Ещё", callback_data=f"submit:{task_id}")],
            [InlineKeyboardButton("« Задание", callback_data=f"task:{task_id}")]
        ])
        result = f"❌ <b>Не пройдено</b> (#{sub_id})\n\n<pre>{safe_output}</pre>"
    await checking.edit_text(result, reply_markup=keyboard, parse_mode="HTML")


@require_admin
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    modules = db.get_modules()
    topics = db.get_topics()
    tasks = db.get_all_tasks()
    text = f"👑 <b>Админ</b>\n\n📦 Модулей: {len(modules)}\n📚 Тем: {len(topics)}\n📝 Заданий: {len(tasks)}"
    await update.message.reply_text(text, reply_markup=admin_menu_keyboard(), parse_mode="HTML")


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
    await update.message.reply_text("✅ Удалено." if db.delete_task(context.args[0]) else "❌ Не найдено.")


@require_admin
async def del_module_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("<code>/delmodule module_id</code>", parse_mode="HTML")
        return
    await update.message.reply_text("✅ Удалено." if db.delete_module(context.args[0]) else "❌ Не найден или есть темы.")


@require_admin
async def del_topic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("<code>/deltopic topic_id</code>", parse_mode="HTML")
        return
    await update.message.reply_text("✅ Удалено." if db.delete_topic(context.args[0]) else "❌ Не найдена или есть задания.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено.", reply_markup=main_menu_keyboard(db.is_admin(update.effective_user.id)))


@require_registered
async def topics_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    student = db.get_student(user.id)
    student_id = student["id"] if student else None
    modules = db.get_modules()
    if not modules:
        await update.message.reply_text("Нет модулей.", reply_markup=back_to_menu_keyboard())
        return
    keyboard = []
    for m in modules:
        topics = db.get_topics_by_module(m["module_id"])
        total = sum(len(db.get_tasks_by_topic(t["topic_id"])) for t in topics)
        solved = sum(1 for t in topics for task in db.get_tasks_by_topic(t["topic_id"]) if student_id and db.has_solved(student_id, task["task_id"]))
        keyboard.append([InlineKeyboardButton(f"📦 {m['name']} ({solved}/{total})", callback_data=f"module:{m['module_id']}")])
    keyboard.append([InlineKeyboardButton("« Меню", callback_data="menu:main")])
    await update.message.reply_text("📦 <b>Модули</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


@require_registered
async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leaders = db.get_leaderboard(15)
    if not leaders:
        await update.message.reply_text("Пусто.", reply_markup=back_to_menu_keyboard())
        return
    text = "🏆 <b>Лидерборд</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for l in leaders:
        name = escape_html(l.get("first_name") or l.get("username") or "???")
        medal = medals[l["rank"]-1] if l["rank"] <= 3 else f"{l['rank']}."
        text += f"{medal} <b>{name}</b> — {l['solved']}✅"
        if l["bonus_points"] > 0:
            text += f" +{l['bonus_points']}⭐"
        text += f" = <b>{l['score']}</b>\n"
    await update.message.reply_text(text, reply_markup=back_to_menu_keyboard(), parse_mode="HTML")


def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("Set BOT_TOKEN!")
        sys.exit(1)
    db.init_db()
    deleted = db.cleanup_old_code()
    if deleted:
        print(f"Cleaned {deleted} old submissions")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("topics", topics_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("deltask", del_task_cmd))
    app.add_handler(CommandHandler("delmodule", del_module_cmd))
    app.add_handler(CommandHandler("deltopic", del_topic_cmd))
    app.add_handler(CommandHandler("gencodes", gen_codes))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu:"))
    app.add_handler(CallbackQueryHandler(modules_callback, pattern="^modules:"))
    app.add_handler(CallbackQueryHandler(module_callback, pattern="^module:"))
    app.add_handler(CallbackQueryHandler(topic_callback, pattern="^topic:"))
    app.add_handler(CallbackQueryHandler(task_callback, pattern="^task:"))
    app.add_handler(CallbackQueryHandler(submit_callback, pattern="^submit:"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))
    app.add_handler(CallbackQueryHandler(create_callback, pattern="^create:"))
    app.add_handler(CallbackQueryHandler(student_callback, pattern="^student:"))
    app.add_handler(CallbackQueryHandler(recent_callback, pattern="^recent:"))
    app.add_handler(CallbackQueryHandler(bytask_callback, pattern="^bytask:"))
    app.add_handler(CallbackQueryHandler(attempts_callback, pattern="^attempts:"))
    app.add_handler(CallbackQueryHandler(code_callback, pattern="^code:"))
    app.add_handler(CallbackQueryHandler(approve_callback, pattern="^approve:"))
    app.add_handler(CallbackQueryHandler(unapprove_callback, pattern="^unapprove:"))
    app.add_handler(CallbackQueryHandler(feedback_callback, pattern="^feedback:"))
    app.add_handler(CallbackQueryHandler(delsub_callback, pattern="^delsub:"))
    app.add_handler(CallbackQueryHandler(assign_callback, pattern="^assign:"))
    app.add_handler(CallbackQueryHandler(assignmod_callback, pattern="^assignmod:"))
    app.add_handler(CallbackQueryHandler(assigntopic_callback, pattern="^assigntopic:"))
    app.add_handler(CallbackQueryHandler(toggleassign_callback, pattern="^toggleassign:"))
    app.add_handler(CallbackQueryHandler(assigned_callback, pattern="^assigned:"))
    app.add_handler(CallbackQueryHandler(unassign_callback, pattern="^unassign:"))
    app.add_handler(CallbackQueryHandler(myattempts_callback, pattern="^myattempts:"))
    app.add_handler(CallbackQueryHandler(mycode_callback, pattern="^mycode:"))
    app.add_handler(CallbackQueryHandler(myassigned_callback, pattern="^myassigned:"))
    app.add_handler(CallbackQueryHandler(editname_callback, pattern="^editname:"))
    app.add_handler(CallbackQueryHandler(hired_callback, pattern="^hired:"))
    app.add_handler(CallbackQueryHandler(archive_callback, pattern="^archive:"))
    app.add_handler(CallbackQueryHandler(skip_feedback_callback, pattern="^skip_feedback:"))
    app.add_handler(CallbackQueryHandler(archived_student_callback, pattern="^archived_student:"))
    app.add_handler(CallbackQueryHandler(restore_callback, pattern="^restore:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.FileExtension("py"), handle_file))
    print("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()