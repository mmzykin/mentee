"""
Telegram Mentor Bot v2 with Full Button Navigation
"""

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
    ConversationHandler,
    ContextTypes,
    filters,
)

import database as db

# ============== CONFIGURATION ==============

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
EXEC_TIMEOUT = 10
ADMIN_USERNAMES = ["qwerty1492"]

WAITING_TASK_DATA = 1


# ============== KEYBOARDS ==============

def main_menu_keyboard(is_admin=False):
    """Main menu buttons."""
    keyboard = [
        [InlineKeyboardButton("📚 Задания", callback_data="back:topics")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="menu:mystats")],
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="menu:admin")])
    return InlineKeyboardMarkup(keyboard)


def admin_menu_keyboard():
    """Admin panel buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📚 Темы", callback_data="admin:topics"),
            InlineKeyboardButton("📝 Задания", callback_data="admin:tasks"),
        ],
        [
            InlineKeyboardButton("👥 Студенты", callback_data="admin:students"),
            InlineKeyboardButton("🎫 Коды", callback_data="admin:codes"),
        ],
        [
            InlineKeyboardButton("➕ Создать коды", callback_data="admin:gencodes"),
        ],
        [InlineKeyboardButton("« Главное меню", callback_data="menu:main")],
    ])


def back_to_menu_keyboard():
    """Simple back to main menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("« Главное меню", callback_data="menu:main")]
    ])


def back_to_admin_keyboard():
    """Back to admin panel."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("« Админ-панель", callback_data="menu:admin")]
    ])


# ============== TASK PARSER ==============

def parse_task_format(text: str) -> Optional[dict]:
    """Parse standardized task format."""
    try:
        topic_match = re.search(r"TOPIC:\s*(\S+)", text)
        task_id_match = re.search(r"TASK_ID:\s*(\S+)", text)
        title_match = re.search(r"TITLE:\s*(.+?)(?:\n|---)", text)
        
        if not all([topic_match, task_id_match, title_match]):
            return None
        
        desc_match = re.search(r"---DESCRIPTION---\s*\n(.*?)---TESTS---", text, re.DOTALL)
        if not desc_match:
            return None
        
        tests_match = re.search(r"---TESTS---\s*\n(.+)", text, re.DOTALL)
        if not tests_match:
            return None
        
        return {
            "topic_id": topic_match.group(1).strip(),
            "task_id": task_id_match.group(1).strip(),
            "title": title_match.group(1).strip(),
            "description": desc_match.group(1).strip(),
            "test_code": tests_match.group(1).strip(),
        }
    except Exception:
        return None


# ============== CODE EXECUTION ==============

def run_code_with_tests(code: str, test_code: str) -> tuple[bool, str]:
    """Execute student code with tests."""
    full_code = code + "\n\n" + test_code
    
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(full_code)
        temp_path = f.name
    
    try:
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT,
            cwd=tempfile.gettempdir(),
        )
        
        output = result.stdout + result.stderr
        passed = result.returncode == 0 and "✅" in output
        
        return passed, output.strip()
    
    except subprocess.TimeoutExpired:
        return False, f"⏰ Timeout: код выполнялся более {EXEC_TIMEOUT} секунд"
    except Exception as e:
        return False, f"❌ Ошибка выполнения: {str(e)}"
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ============== HELPER FUNCTIONS ==============

def require_admin(func):
    """Decorator to require admin access."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not db.is_admin(user_id):
            await update.message.reply_text("⛔ Только для администраторов.")
            return
        return await func(update, context)
    return wrapper


def require_registered(func):
    """Decorator to require student registration."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if db.is_admin(user_id):
            return await func(update, context)
        if not db.is_registered(user_id):
            await update.message.reply_text(
                "⛔ Сначала зарегистрируйся!\n"
                "Используй: /register КОД"
            )
            return
        return await func(update, context)
    return wrapper


# ============== BASIC COMMANDS ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    name = escape_html(user.first_name)
    
    # Hardcoded admins
    if user.username and user.username.lower() in ADMIN_USERNAMES:
        if not db.is_admin(user.id):
            db.add_admin(user.id)
            await update.message.reply_text(
                f"👑 <b>{name}</b>, ты теперь админ!",
                reply_markup=main_menu_keyboard(is_admin=True),
                parse_mode="HTML"
            )
            return
    
    # First user becomes admin
    if db.get_admin_count() == 0:
        db.add_admin(user.id)
        await update.message.reply_text(
            f"👑 <b>{name}</b>, ты первый — теперь ты админ!",
            reply_markup=main_menu_keyboard(is_admin=True),
            parse_mode="HTML"
        )
        return
    
    if db.is_admin(user.id):
        await update.message.reply_text(
            f"👑 С возвращением, <b>{name}</b>!",
            reply_markup=main_menu_keyboard(is_admin=True),
            parse_mode="HTML"
        )
        return
    
    student = db.get_student(user.id)
    if student:
        await update.message.reply_text(
            f"👋 С возвращением, <b>{name}</b>!",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML"
        )
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 У меня есть код", callback_data="menu:register")]
        ])
        await update.message.reply_text(
            f"👋 Привет, <b>{name}</b>!\n\n"
            "Для доступа нужна регистрация.\n"
            "Получи код у ментора.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    user = update.effective_user
    is_admin = db.is_admin(user.id)
    
    text = (
        "📖 <b>Команды</b>\n\n"
        "/start — главное меню\n"
        "/topics — задания\n"
        "/mystats — статистика\n"
    )
    
    if is_admin:
        text += (
            "\n👑 <b>Админ</b>\n"
            "/admin — панель\n"
            "/gencodes N — коды\n"
            "/addtopic id name\n"
            "/addtask — задание\n"
        )
    
    await update.message.reply_text(text, reply_markup=main_menu_keyboard(is_admin), parse_mode="HTML")


# ============== REGISTRATION ==============

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /register command."""
    user = update.effective_user
    name = escape_html(user.first_name)
    
    if db.is_registered(user.id):
        await update.message.reply_text(
            "✅ Ты уже зарегистрирован!",
            reply_markup=main_menu_keyboard()
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "Используй: /register КОД\n"
            "Пример: <code>/register ABC123XY</code>",
            parse_mode="HTML"
        )
        return
    
    code = context.args[0].upper()
    
    success = db.register_student(
        user_id=user.id,
        username=user.username or "",
        first_name=user.first_name or "",
        code=code
    )
    
    if success:
        await update.message.reply_text(
            f"✅ Добро пожаловать, <b>{name}</b>!",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ Неверный или использованный код.")


# ============== MENU CALLBACKS ==============

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu navigation."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    is_admin = db.is_admin(user.id)
    action = query.data.split(":")[1]
    
    if action == "main":
        await query.edit_message_text(
            "🏠 <b>Главное меню</b>",
            reply_markup=main_menu_keyboard(is_admin),
            parse_mode="HTML"
        )
    
    elif action == "mystats":
        student = db.get_student(user.id)
        if not student:
            await query.edit_message_text(
                "Ты не зарегистрирован.",
                reply_markup=back_to_menu_keyboard()
            )
            return
        
        stats = db.get_student_stats(student["id"])
        text = (
            f"📊 <b>Твоя статистика</b>\n\n"
            f"✅ Решено: <b>{stats['solved_tasks']}</b> из {stats['total_tasks']}\n"
            f"📤 Отправок: <b>{stats['total_submissions']}</b>"
        )
        await query.edit_message_text(text, reply_markup=back_to_menu_keyboard(), parse_mode="HTML")
    
    elif action == "admin":
        if not is_admin:
            await query.edit_message_text("⛔ Нет доступа")
            return
        
        topics = db.get_topics()
        tasks = db.get_all_tasks()
        students = db.get_all_students()
        codes = db.get_unused_codes()
        
        text = (
            "👑 <b>Админ-панель</b>\n\n"
            f"📚 Тем: <b>{len(topics)}</b>\n"
            f"📝 Заданий: <b>{len(tasks)}</b>\n"
            f"👥 Студентов: <b>{len(students)}</b>\n"
            f"🎫 Кодов: <b>{len(codes)}</b>"
        )
        await query.edit_message_text(text, reply_markup=admin_menu_keyboard(), parse_mode="HTML")
    
    elif action == "register":
        await query.edit_message_text(
            "Отправь команду:\n<code>/register ТВОЙ_КОД</code>",
            parse_mode="HTML"
        )


# ============== ADMIN CALLBACKS ==============

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin actions."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    if not db.is_admin(user.id):
        await query.edit_message_text("⛔ Нет доступа")
        return
    
    action = query.data.split(":")[1]
    
    if action == "topics":
        topics = db.get_topics()
        if not topics:
            text = "Нет тем.\n\nДобавить: <code>/addtopic id название</code>"
        else:
            text = "📚 <b>Темы</b>\n\n"
            for t in topics:
                tasks_count = len(db.get_tasks_by_topic(t["topic_id"]))
                text += f"• <b>{t['topic_id']}</b> — {escape_html(t['name'])} ({tasks_count})\n"
            text += "\nДобавить: <code>/addtopic id название</code>"
        await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode="HTML")
    
    elif action == "tasks":
        topics = db.get_topics()
        if not topics:
            text = "Сначала создай тему: /addtopic"
        else:
            text = "📝 <b>Задания</b>\n\n"
            for topic in topics:
                tasks = db.get_tasks_by_topic(topic["topic_id"])
                text += f"<b>{escape_html(topic['name'])}</b>\n"
                if tasks:
                    for task in tasks:
                        text += f"  • <code>{task['task_id']}</code>: {escape_html(task['title'])}\n"
                else:
                    text += "  <i>(пусто)</i>\n"
                text += "\n"
            text += "Добавить: /addtask"
        await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode="HTML")
    
    elif action == "students":
        students = db.get_all_students_stats()
        if not students:
            await query.edit_message_text(
                "<i>Пока нет студентов.</i>",
                reply_markup=back_to_admin_keyboard(),
                parse_mode="HTML"
            )
            return
        
        keyboard = []
        for s in students:
            name = s.get("first_name") or s.get("username") or str(s["user_id"])
            btn_text = f"{name}: {s['solved_tasks']}/{s['total_tasks']} ✅"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"student:{s['user_id']}")])
        
        keyboard.append([InlineKeyboardButton("« Админ-панель", callback_data="menu:admin")])
        
        await query.edit_message_text(
            "👥 <b>Студенты</b>\n\nНажми чтобы посмотреть:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    
    elif action == "codes":
        codes = db.get_unused_codes()
        if not codes:
            text = "<i>Нет свободных кодов.</i>"
        else:
            text = f"🎫 <b>Коды</b> ({len(codes)})\n\n"
            for c in codes:
                text += f"<code>{c['code']}</code>\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Создать ещё", callback_data="admin:gencodes")],
            [InlineKeyboardButton("« Назад", callback_data="menu:admin")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    
    elif action == "gencodes":
        codes = db.create_codes(5)
        text = f"🎫 <b>Созданы коды</b>\n\n"
        for c in codes:
            text += f"<code>{c}</code>\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Ещё 5", callback_data="admin:gencodes")],
            [InlineKeyboardButton("« Админ-панель", callback_data="menu:admin")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


# ============== STUDENT VIEW CALLBACKS ==============

async def student_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show student details with task buttons."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    if not db.is_admin(user.id):
        await query.edit_message_text("⛔ Нет доступа")
        return
    
    user_id = int(query.data.split(":")[1])
    student = db.get_student(user_id)
    
    if not student:
        await query.edit_message_text("Студент не найден.")
        return
    
    name = escape_html(student.get("first_name") or student.get("username") or str(user_id))
    stats = db.get_student_stats(student["id"])
    
    text = (
        f"📋 <b>{name}</b>\n"
        f"ID: <code>{user_id}</code>\n"
        f"Код: <code>{student['code_used']}</code>\n\n"
        f"✅ Решено: <b>{stats['solved_tasks']}</b>/{stats['total_tasks']}\n"
        f"📤 Отправок: <b>{stats['total_submissions']}</b>\n\n"
        "Нажми на задание чтобы увидеть попытки:"
    )
    
    # Get tasks with submissions
    keyboard = []
    for topic in db.get_topics():
        tasks = db.get_tasks_by_topic(topic["topic_id"])
        for task in tasks:
            submissions = db.get_student_submissions(student["id"], task["task_id"])
            if submissions:
                solved = db.has_solved(student["id"], task["task_id"])
                status = "✅" if solved else "❌"
                btn_text = f"{status} {task['task_id']}: {len(submissions)} попыт."
                keyboard.append([InlineKeyboardButton(
                    btn_text, 
                    callback_data=f"attempts:{student['id']}:{task['task_id']}"
                )])
    
    if not keyboard:
        text += "\n\n<i>Нет попыток</i>"
    
    keyboard.append([InlineKeyboardButton("« К студентам", callback_data="admin:students")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def attempts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show student attempts for a task."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    if not db.is_admin(user.id):
        await query.edit_message_text("⛔ Нет доступа")
        return
    
    parts = query.data.split(":")
    student_id = int(parts[1])
    task_id = parts[2]
    
    student = db.get_student_by_id(student_id)
    task = db.get_task(task_id)
    
    if not student or not task:
        await query.edit_message_text("Не найдено.")
        return
    
    submissions = db.get_student_submissions(student_id, task_id)
    
    name = escape_html(student.get("first_name") or student.get("username") or "")
    
    text = (
        f"📝 <b>{escape_html(task['title'])}</b>\n"
        f"Студент: <b>{name}</b>\n"
        f"Попыток: <b>{len(submissions)}</b>\n\n"
        "Нажми чтобы посмотреть код:"
    )
    
    keyboard = []
    for i, sub in enumerate(submissions, 1):
        status = "✅" if sub["passed"] else "❌"
        time = sub["submitted_at"][11:16] if sub["submitted_at"] else ""
        date = sub["submitted_at"][:10] if sub["submitted_at"] else ""
        btn_text = f"{status} #{i} — {date} {time}"
        keyboard.append([InlineKeyboardButton(
            btn_text,
            callback_data=f"code:{sub['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show submission code."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    if not db.is_admin(user.id):
        await query.edit_message_text("⛔ Нет доступа")
        return
    
    submission_id = int(query.data.split(":")[1])
    submission = db.get_submission_by_id(submission_id)
    
    if not submission:
        await query.edit_message_text("Не найдено.")
        return
    
    status = "✅ Пройдено" if submission["passed"] else "❌ Не пройдено"
    code = submission["code"]
    
    # Truncate if too long
    if len(code) > 3500:
        code = code[:3500] + "\n... (сокращено)"
    
    text = (
        f"<b>{status}</b>\n"
        f"Задание: <code>{submission['task_id']}</code>\n"
        f"Время: {submission['submitted_at']}\n\n"
        f"<b>Код:</b>\n<pre>{escape_html(code)}</pre>"
    )
    
    # Get student_id and task_id for back button
    student_id = submission["student_id"]
    task_id = submission["task_id"]
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("« К попыткам", callback_data=f"attempts:{student_id}:{task_id}")]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


# ============== TOPICS & TASKS CALLBACKS ==============

async def topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show tasks in a topic."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    student = db.get_student(user.id)
    student_id = student["id"] if student else None
    
    topic_id = query.data.split(":")[1]
    topic = db.get_topic(topic_id)
    
    if not topic:
        await query.edit_message_text("Тема не найдена.")
        return
    
    tasks = db.get_tasks_by_topic(topic_id)
    
    keyboard = []
    for task in tasks:
        if student_id and db.has_solved(student_id, task["task_id"]):
            status = "✅"
        else:
            status = "⬜"
        btn_text = f"{status} {task['task_id']}: {task['title']}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"task:{task['task_id']}")])
    
    keyboard.append([InlineKeyboardButton("« Назад", callback_data="back:topics")])
    
    await query.edit_message_text(
        f"📂 <b>{escape_html(topic['name'])}</b>\n\nВыбери задание:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show task details with submit button."""
    query = update.callback_query
    await query.answer()
    
    task_id = query.data.split(":")[1]
    task = db.get_task(task_id)
    
    if not task:
        await query.edit_message_text("Задание не найдено.")
        return
    
    description = task['description']
    if len(description) > 3500:
        description = description[:3500] + "\n\n... (сокращено)"
    
    text = f"📝 <b>{escape_html(task['title'])}</b>\nID: <code>{task_id}</code>\n\n{description}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Отправить решение", callback_data=f"submit:{task_id}")],
        [InlineKeyboardButton("« Назад", callback_data=f"topic:{task['topic_id']}")]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard)


async def submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start submission from button."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    if not db.is_registered(user.id) and not db.is_admin(user.id):
        await query.edit_message_text("⛔ Сначала зарегистрируйся!")
        return
    
    task_id = query.data.split(":")[1]
    task = db.get_task(task_id)
    
    if not task:
        await query.edit_message_text("Задание не найдено.")
        return
    
    context.user_data["pending_task"] = task_id
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отмена", callback_data=f"task:{task_id}")]
    ])
    
    await query.edit_message_text(
        f"📤 <b>{escape_html(task['title'])}</b>\n\n"
        "Отправь код следующим сообщением.\n"
        "Текст или файл <code>.py</code>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back button."""
    query = update.callback_query
    await query.answer()
    
    target = query.data.split(":")[1]
    
    if target == "topics":
        user = update.effective_user
        student = db.get_student(user.id)
        student_id = student["id"] if student else None
        is_admin = db.is_admin(user.id)
        
        topics = db.get_topics()
        keyboard = []
        
        for topic in topics:
            tasks = db.get_tasks_by_topic(topic["topic_id"])
            solved = sum(1 for t in tasks if student_id and db.has_solved(student_id, t["task_id"]))
            total = len(tasks)
            
            if total > 0:
                btn_text = f"{topic['name']} ({solved}/{total})"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"topic:{topic['topic_id']}")])
        
        keyboard.append([InlineKeyboardButton("« Главное меню", callback_data="menu:main")])
        
        await query.edit_message_text(
            "📚 <b>Выбери тему</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )


# ============== COMMAND HANDLERS ==============

@require_registered
async def topics_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show topics with buttons."""
    user = update.effective_user
    student = db.get_student(user.id)
    student_id = student["id"] if student else None
    
    topics = db.get_topics()
    
    if not topics:
        await update.message.reply_text("Пока нет тем.", reply_markup=back_to_menu_keyboard())
        return
    
    keyboard = []
    for topic in topics:
        tasks = db.get_tasks_by_topic(topic["topic_id"])
        solved = sum(1 for t in tasks if student_id and db.has_solved(student_id, t["task_id"]))
        total = len(tasks)
        
        if total > 0:
            btn_text = f"{topic['name']} ({solved}/{total})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"topic:{topic['topic_id']}")])
    
    keyboard.append([InlineKeyboardButton("« Главное меню", callback_data="menu:main")])
    
    await update.message.reply_text(
        "📚 <b>Выбери тему</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


@require_registered
async def show_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show task description."""
    if not context.args:
        await update.message.reply_text("Используй: <code>/task id</code>", parse_mode="HTML")
        return
    
    task_id = context.args[0]
    task = db.get_task(task_id)
    
    if not task:
        await update.message.reply_text(f"❌ Задание <code>{task_id}</code> не найдено.", parse_mode="HTML")
        return
    
    text = f"📝 {task['title']}\nID: {task_id}\n\n{task['description']}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Отправить решение", callback_data=f"submit:{task_id}")],
        [InlineKeyboardButton("« К темам", callback_data="back:topics")]
    ])
    
    await update.message.reply_text(text, reply_markup=keyboard)


@require_registered
async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start submission."""
    if not context.args:
        await update.message.reply_text("Используй: <code>/submit id</code>", parse_mode="HTML")
        return
    
    task_id = context.args[0]
    task = db.get_task(task_id)
    
    if not task:
        await update.message.reply_text(f"❌ Задание <code>{task_id}</code> не найдено.", parse_mode="HTML")
        return
    
    context.user_data["pending_task"] = task_id
    
    await update.message.reply_text(
        f"📤 <b>{escape_html(task['title'])}</b>\n\n"
        "Отправь код следующим сообщением.\n"
        "Отмена: /cancel",
        parse_mode="HTML"
    )


@require_registered
async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show student's stats."""
    user = update.effective_user
    student = db.get_student(user.id)
    
    if not student:
        await update.message.reply_text("Ты не зарегистрирован.")
        return
    
    stats = db.get_student_stats(student["id"])
    
    text = (
        f"📊 <b>Твоя статистика</b>\n\n"
        f"✅ Решено: <b>{stats['solved_tasks']}</b> из {stats['total_tasks']}\n"
        f"📤 Отправок: <b>{stats['total_submissions']}</b>"
    )
    
    await update.message.reply_text(text, reply_markup=main_menu_keyboard(), parse_mode="HTML")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation."""
    context.user_data.clear()
    user = update.effective_user
    is_admin = db.is_admin(user.id)
    await update.message.reply_text("❌ Отменено.", reply_markup=main_menu_keyboard(is_admin))
    return ConversationHandler.END


async def handle_code_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle code from student."""
    task_id = context.user_data.get("pending_task")
    if not task_id:
        return
    
    user = update.effective_user
    student = db.get_student(user.id)
    is_admin = db.is_admin(user.id)
    
    if not student and not is_admin:
        await update.message.reply_text("⛔ Сначала зарегистрируйся!")
        return
    
    if not student:
        student = {"id": 0}
    
    # Get code
    code = None
    if update.message.document:
        if update.message.document.file_name.endswith(".py"):
            file = await update.message.document.get_file()
            file_bytes = await file.download_as_bytearray()
            code = file_bytes.decode("utf-8")
        else:
            await update.message.reply_text("❌ Нужен файл .py")
            return
    elif update.message.text:
        code = update.message.text
        if code.startswith("```"):
            lines = code.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines)
    
    if not code:
        await update.message.reply_text("❌ Не удалось получить код.")
        return
    
    del context.user_data["pending_task"]
    
    task = db.get_task(task_id)
    if not task:
        await update.message.reply_text("❌ Задание не найдено.")
        return
    
    checking = await update.message.reply_text("⏳ Проверяю...")
    passed, output = run_code_with_tests(code, task["test_code"])
    
    if student["id"] != 0:
        db.add_submission(student["id"], task_id, code, passed, output)
    
    safe_output = escape_html(output[:1500])
    
    if passed:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎉 К темам", callback_data="back:topics")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")]
        ])
        result = f"✅ <b>Задание {task_id} выполнено!</b>\n\n<pre>{safe_output}</pre>"
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Ещё раз", callback_data=f"submit:{task_id}")],
            [InlineKeyboardButton("« К заданию", callback_data=f"task:{task_id}")]
        ])
        result = f"❌ <b>Не пройдено</b>\n\n<pre>{safe_output}</pre>"
    
    await checking.edit_text(result, reply_markup=keyboard, parse_mode="HTML")


# ============== ADMIN COMMANDS ==============

@require_admin
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel."""
    topics = db.get_topics()
    tasks = db.get_all_tasks()
    students = db.get_all_students()
    codes = db.get_unused_codes()
    
    text = (
        "👑 <b>Админ-панель</b>\n\n"
        f"📚 Тем: <b>{len(topics)}</b>\n"
        f"📝 Заданий: <b>{len(tasks)}</b>\n"
        f"👥 Студентов: <b>{len(students)}</b>\n"
        f"🎫 Кодов: <b>{len(codes)}</b>"
    )
    
    await update.message.reply_text(text, reply_markup=admin_menu_keyboard(), parse_mode="HTML")


@require_admin
async def gen_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate registration codes."""
    count = 5
    if context.args:
        try:
            count = int(context.args[0])
            count = max(1, min(50, count))
        except ValueError:
            pass
    
    codes = db.create_codes(count)
    text = f"🎫 <b>Созданы {len(codes)} кодов</b>\n\n"
    for c in codes:
        text += f"<code>{c}</code>\n"
    
    await update.message.reply_text(text, reply_markup=back_to_admin_keyboard(), parse_mode="HTML")


@require_admin
async def show_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show unused codes."""
    codes = db.get_unused_codes()
    
    if not codes:
        text = "<i>Нет свободных кодов.</i>"
    else:
        text = f"🎫 <b>Коды</b> ({len(codes)})\n\n"
        for c in codes:
            text += f"<code>{c['code']}</code>\n"
    
    await update.message.reply_text(text, reply_markup=back_to_admin_keyboard(), parse_mode="HTML")


@require_admin
async def add_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a new topic."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "Используй: <code>/addtopic id название</code>",
            parse_mode="HTML"
        )
        return
    
    topic_id = context.args[0]
    name = " ".join(context.args[1:])
    
    topics = db.get_topics()
    order = len(topics) + 1
    
    if db.add_topic(topic_id, name, order):
        await update.message.reply_text(
            f"✅ Тема добавлена: <b>{topic_id}</b> — {escape_html(name)}",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(f"❌ Тема <code>{topic_id}</code> уже существует.", parse_mode="HTML")


@require_admin
async def del_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a topic."""
    if not context.args:
        await update.message.reply_text("Используй: <code>/deltopic id</code>", parse_mode="HTML")
        return
    
    topic_id = context.args[0]
    
    if db.delete_topic(topic_id):
        await update.message.reply_text(
            f"✅ Тема <code>{topic_id}</code> удалена.",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ Не удалось удалить. Есть задания?")


@require_admin
async def add_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding a task."""
    topics = db.get_topics()
    
    if not topics:
        await update.message.reply_text("❌ Сначала создай тему: /addtopic")
        return ConversationHandler.END
    
    topics_list = "\n".join(f"• <code>{t['topic_id']}</code> — {escape_html(t['name'])}" for t in topics)
    
    await update.message.reply_text(
        f"📝 <b>Добавление задания</b>\n\n"
        f"Темы:\n{topics_list}\n\n"
        "Отправь задание в формате:\n\n"
        "<code>TOPIC: topic_id\n"
        "TASK_ID: task_id\n"
        "TITLE: Название\n"
        "---DESCRIPTION---\n"
        "Описание...\n"
        "---TESTS---\n"
        "def test():\n"
        "    ...\n"
        "test()</code>\n\n"
        "Отмена: /cancel",
        parse_mode="HTML"
    )
    return WAITING_TASK_DATA


async def add_task_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and parse task data."""
    text = update.message.text
    
    parsed = parse_task_format(text)
    if not parsed:
        await update.message.reply_text("❌ Неверный формат. Попробуй снова или /cancel")
        return WAITING_TASK_DATA
    
    topic = db.get_topic(parsed["topic_id"])
    if not topic:
        await update.message.reply_text(f"❌ Тема <code>{parsed['topic_id']}</code> не найдена.", parse_mode="HTML")
        return WAITING_TASK_DATA
    
    if db.get_task(parsed["task_id"]):
        await update.message.reply_text(f"❌ Задание <code>{parsed['task_id']}</code> уже есть.", parse_mode="HTML")
        return WAITING_TASK_DATA
    
    success = db.add_task(
        task_id=parsed["task_id"],
        topic_id=parsed["topic_id"],
        title=parsed["title"],
        description=parsed["description"],
        test_code=parsed["test_code"]
    )
    
    if success:
        await update.message.reply_text(
            f"✅ <b>Задание добавлено!</b>\n\n"
            f"ID: <code>{parsed['task_id']}</code>\n"
            f"Тема: {escape_html(topic['name'])}\n"
            f"Название: {escape_html(parsed['title'])}",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ Ошибка.")
    
    return ConversationHandler.END


@require_admin
async def del_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a task."""
    if not context.args:
        await update.message.reply_text("Используй: <code>/deltask task_id</code>", parse_mode="HTML")
        return
    
    task_id = context.args[0]
    task = db.get_task(task_id)
    
    if not task:
        await update.message.reply_text(f"❌ Задание <code>{task_id}</code> не найдено.", parse_mode="HTML")
        return
    
    if db.delete_task(task_id):
        await update.message.reply_text(
            f"✅ Задание <code>{task_id}</code> удалено.",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ Ошибка.")


@require_admin
async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all tasks."""
    topics = db.get_topics()
    
    if not topics:
        await update.message.reply_text("Нет тем.", reply_markup=back_to_admin_keyboard())
        return
    
    text = "📚 <b>Все задания</b>\n\n"
    
    for topic in topics:
        tasks = db.get_tasks_by_topic(topic["topic_id"])
        text += f"<b>{escape_html(topic['name'])}</b>\n"
        if tasks:
            for task in tasks:
                text += f"  • <code>{task['task_id']}</code>: {escape_html(task['title'])}\n"
        else:
            text += "  <i>(пусто)</i>\n"
        text += "\n"
    
    await update.message.reply_text(text, reply_markup=back_to_admin_keyboard(), parse_mode="HTML")


@require_admin
async def list_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all students."""
    students = db.get_all_students_stats()
    
    if not students:
        await update.message.reply_text("<i>Пока нет студентов.</i>", reply_markup=back_to_admin_keyboard(), parse_mode="HTML")
        return
    
    text = "👥 <b>Студенты</b>\n\n"
    for s in students:
        name = escape_html(s.get("first_name") or s.get("username") or str(s["user_id"]))
        text += f"• <b>{name}</b>: {s['solved_tasks']}/{s['total_tasks']} ✅, {s['total_submissions']} отпр.\n"
    
    await update.message.reply_text(text, reply_markup=back_to_admin_keyboard(), parse_mode="HTML")


@require_admin
async def student_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show student details."""
    if not context.args:
        await update.message.reply_text("Используй: <code>/student user_id</code>", parse_mode="HTML")
        return
    
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")
        return
    
    student = db.get_student(user_id)
    if not student:
        await update.message.reply_text(f"Студент {user_id} не найден.")
        return
    
    name = escape_html(student.get("first_name") or student.get("username") or str(user_id))
    stats = db.get_student_stats(student["id"])
    
    text = (
        f"📋 <b>{name}</b>\n"
        f"ID: <code>{user_id}</code>\n"
        f"Код: <code>{student['code_used']}</code>\n\n"
        f"✅ Решено: <b>{stats['solved_tasks']}</b>/{stats['total_tasks']}\n"
        f"📤 Отправок: <b>{stats['total_submissions']}</b>"
    )
    
    await update.message.reply_text(text, reply_markup=back_to_admin_keyboard(), parse_mode="HTML")


# ============== MAIN ==============

def main():
    """Start the bot."""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Set BOT_TOKEN!")
        sys.exit(1)
    
    db.init_db()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    task_conv = ConversationHandler(
        entry_points=[CommandHandler("addtask", add_task_start)],
        states={
            WAITING_TASK_DATA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_receive)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("register", register))
    
    # Admin
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("gencodes", gen_codes))
    app.add_handler(CommandHandler("codes", show_codes))
    app.add_handler(CommandHandler("addtopic", add_topic))
    app.add_handler(CommandHandler("deltopic", del_topic))
    app.add_handler(task_conv)
    app.add_handler(CommandHandler("tasks", list_tasks))
    app.add_handler(CommandHandler("deltask", del_task))
    app.add_handler(CommandHandler("students", list_students))
    app.add_handler(CommandHandler("student", student_detail))
    
    # Student
    app.add_handler(CommandHandler("topics", topics_list))
    app.add_handler(CommandHandler("task", show_task))
    app.add_handler(CommandHandler("submit", submit_start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("mystats", my_stats))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu:"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))
    app.add_handler(CallbackQueryHandler(student_callback, pattern="^student:"))
    app.add_handler(CallbackQueryHandler(attempts_callback, pattern="^attempts:"))
    app.add_handler(CallbackQueryHandler(code_callback, pattern="^code:"))
    app.add_handler(CallbackQueryHandler(topic_callback, pattern="^topic:"))
    app.add_handler(CallbackQueryHandler(task_callback, pattern="^task:"))
    app.add_handler(CallbackQueryHandler(submit_callback, pattern="^submit:"))
    app.add_handler(CallbackQueryHandler(back_callback, pattern="^back:"))
    
    # Code submissions
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code_submission))
    app.add_handler(MessageHandler(filters.Document.FileExtension("py"), handle_code_submission))
    
    print("🤖 Mentor Bot v2 starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
