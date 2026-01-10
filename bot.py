"""
Telegram Mentor Bot v2 with Inline Buttons
- SQLite database for students, tasks, submissions
- Registration with unique codes
- Admin panel for managing tasks
- Convenient button navigation
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

# Conversation states
(
    WAITING_CODE,
    WAITING_TASK_DATA,
    WAITING_TOPIC_DATA,
    CONFIRM_DELETE,
) = range(4)


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
                "Используй: /register <КОД>\n"
                "Код получи у ментора."
            )
            return
        return await func(update, context)
    return wrapper


# ============== BASIC COMMANDS ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    
    if db.get_admin_count() == 0:
        db.add_admin(user.id)
        await update.message.reply_text(
            f"👑 {user.first_name}, ты первый пользователь — теперь ты админ!\n\n"
            "Админ-команды:\n"
            "/admin — панель управления\n"
            "/gencodes 5 — создать 5 кодов\n"
            "/addtopic — добавить тему\n"
            "/addtask — добавить задание\n"
            "/students — список студентов\n\n"
            "Начни с /addtopic чтобы создать первую тему!"
        )
        return
    
    if db.is_admin(user.id):
        await update.message.reply_text(
            f"👑 С возвращением, {user.first_name}!\n\n"
            "/admin — панель управления\n"
            "/topics — задания"
        )
        return
    
    student = db.get_student(user.id)
    if student:
        keyboard = [[InlineKeyboardButton("📚 Задания", callback_data="back:topics")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"👋 С возвращением, {user.first_name}!",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            "Для доступа к заданиям нужна регистрация.\n"
            "Используй: /register <КОД>\n\n"
            "Код получи у ментора."
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    user = update.effective_user
    
    base_help = (
        "📖 **Команды:**\n\n"
        "/topics — список тем и заданий\n"
        "/task <id> — посмотреть задание\n"
        "/submit <id> — отправить решение\n"
        "/mystats — твоя статистика\n"
    )
    
    if db.is_admin(user.id):
        base_help += (
            "\n👑 **Админ-команды:**\n"
            "/admin — панель управления\n"
            "/gencodes <N> — создать N кодов\n"
            "/codes — показать свободные коды\n"
            "/addtopic <id> <название> — добавить тему\n"
            "/addtask — добавить задание\n"
            "/deltask <id> — удалить задание\n"
            "/students — список студентов\n"
            "/student <user_id> — инфо о студенте\n"
        )
    
    await update.message.reply_text(base_help, parse_mode="Markdown")


# ============== REGISTRATION ==============

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /register command."""
    user = update.effective_user
    
    if db.is_registered(user.id):
        await update.message.reply_text("✅ Ты уже зарегистрирован!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Используй: /register <КОД>\n"
            "Пример: /register ABC123XY"
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
        keyboard = [[InlineKeyboardButton("📚 К заданиям", callback_data="back:topics")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"✅ Регистрация успешна!\n\n"
            f"Добро пожаловать, {user.first_name}!",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "❌ Неверный или уже использованный код.\n"
            "Проверь код и попробуй снова."
        )


# ============== ADMIN: CODES ==============

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
    codes_text = "\n".join(f"`{c}`" for c in codes)
    await update.message.reply_text(
        f"🎫 Созданы {len(codes)} кодов:\n\n{codes_text}\n\n"
        "Отправь коды студентам для регистрации.",
        parse_mode="Markdown"
    )


@require_admin
async def show_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show unused codes."""
    codes = db.get_unused_codes()
    
    if not codes:
        await update.message.reply_text("Нет свободных кодов.\nСоздать: /gencodes 5")
        return
    
    codes_text = "\n".join(f"`{c['code']}`" for c in codes)
    await update.message.reply_text(
        f"🎫 Свободные коды ({len(codes)}):\n\n{codes_text}",
        parse_mode="Markdown"
    )


# ============== ADMIN: TOPICS ==============

@require_admin
async def add_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a new topic."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "Используй: /addtopic <id> <название>\n"
            "Пример: /addtopic 1 Переменные"
        )
        return
    
    topic_id = context.args[0]
    name = " ".join(context.args[1:])
    
    topics = db.get_topics()
    order = len(topics) + 1
    
    if db.add_topic(topic_id, name, order):
        await update.message.reply_text(
            f"✅ Тема добавлена:\nID: `{topic_id}`\nНазвание: {name}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ Тема `{topic_id}` уже существует.")


@require_admin
async def del_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a topic."""
    if not context.args:
        await update.message.reply_text("Используй: /deltopic <id>")
        return
    
    topic_id = context.args[0]
    
    if db.delete_topic(topic_id):
        await update.message.reply_text(f"✅ Тема `{topic_id}` удалена.")
    else:
        await update.message.reply_text(
            f"❌ Не удалось удалить `{topic_id}`.\n"
            "Возможно, в теме есть задания."
        )


# ============== ADMIN: TASKS ==============

@require_admin
async def add_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding a task."""
    topics = db.get_topics()
    
    if not topics:
        await update.message.reply_text(
            "❌ Сначала создай хотя бы одну тему!\n"
            "Используй: /addtopic <id> <название>"
        )
        return ConversationHandler.END
    
    topics_list = "\n".join(f"• `{t['topic_id']}` — {t['name']}" for t in topics)
    
    await update.message.reply_text(
        "📝 **Добавление задания**\n\n"
        f"Доступные темы:\n{topics_list}\n\n"
        "Отправь задание в формате:\n"
        "```\n"
        "TOPIC: topic_id\n"
        "TASK_ID: task_id\n"
        "TITLE: Название\n"
        "---DESCRIPTION---\n"
        "Описание...\n"
        "---TESTS---\n"
        "def test():\n"
        "    assert func(1) == 2\n"
        "    print(\"✅ All tests passed!\")\n"
        "test()\n"
        "```\n\n"
        "Отмена: /cancel",
        parse_mode="Markdown"
    )
    return WAITING_TASK_DATA


async def add_task_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and parse task data."""
    text = update.message.text
    
    parsed = parse_task_format(text)
    if not parsed:
        await update.message.reply_text(
            "❌ Неверный формат. Попробуй снова или /cancel"
        )
        return WAITING_TASK_DATA
    
    topic = db.get_topic(parsed["topic_id"])
    if not topic:
        await update.message.reply_text(f"❌ Тема `{parsed['topic_id']}` не найдена.")
        return WAITING_TASK_DATA
    
    if db.get_task(parsed["task_id"]):
        await update.message.reply_text(f"❌ Задание `{parsed['task_id']}` уже существует.")
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
            f"✅ Задание добавлено!\n\n"
            f"ID: `{parsed['task_id']}`\n"
            f"Тема: {topic['name']}\n"
            f"Название: {parsed['title']}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Ошибка при добавлении.")
    
    return ConversationHandler.END


@require_admin
async def del_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a task."""
    if not context.args:
        await update.message.reply_text("Используй: /deltask <task_id>")
        return
    
    task_id = context.args[0]
    task = db.get_task(task_id)
    
    if not task:
        await update.message.reply_text(f"❌ Задание `{task_id}` не найдено.")
        return
    
    if db.delete_task(task_id):
        await update.message.reply_text(f"✅ Задание `{task_id}` удалено.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Ошибка при удалении.")


@require_admin
async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all tasks."""
    topics = db.get_topics()
    
    if not topics:
        await update.message.reply_text("Нет тем. Создай: /addtopic")
        return
    
    text = "📚 **Все задания:**\n\n"
    
    for topic in topics:
        tasks = db.get_tasks_by_topic(topic["topic_id"])
        text += f"**{topic['name']}** (`{topic['topic_id']}`)\n"
        
        if tasks:
            for task in tasks:
                text += f"  • `{task['task_id']}` — {task['title']}\n"
        else:
            text += "  _(нет заданий)_\n"
        text += "\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")


# ============== ADMIN: STUDENTS ==============

@require_admin
async def list_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all students with stats."""
    students = db.get_all_students_stats()
    
    if not students:
        await update.message.reply_text("Пока нет студентов.")
        return
    
    text = "👥 **Студенты:**\n\n"
    
    for s in students:
        name = s.get("first_name") or s.get("username") or str(s["user_id"])
        text += (
            f"• **{name}** (`{s['user_id']}`)\n"
            f"  ✅ {s['solved_tasks']}/{s['total_tasks']}, "
            f"📤 {s['total_submissions']} отправок\n"
        )
    
    await update.message.reply_text(text, parse_mode="Markdown")


@require_admin
async def student_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed stats for a student."""
    if not context.args:
        await update.message.reply_text("Используй: /student <user_id>")
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
    
    name = student.get("first_name") or student.get("username") or str(user_id)
    stats = db.get_student_stats(student["id"])
    
    text = (
        f"📋 **{name}**\n"
        f"ID: `{user_id}`\n"
        f"Код: `{student['code_used']}`\n\n"
        f"✅ Решено: {stats['solved_tasks']}/{stats['total_tasks']}\n"
        f"📤 Отправок: {stats['total_submissions']}\n\n"
        "**По темам:**\n"
    )
    
    for topic in db.get_topics():
        tasks = db.get_tasks_by_topic(topic["topic_id"])
        solved = sum(1 for t in tasks if db.has_solved(student["id"], t["task_id"]))
        text += f"• {topic['name']}: {solved}/{len(tasks)}\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")


@require_admin
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel."""
    topics = db.get_topics()
    tasks = db.get_all_tasks()
    students = db.get_all_students()
    codes = db.get_unused_codes()
    
    text = (
        "👑 **Панель администратора**\n\n"
        f"📚 Тем: {len(topics)}\n"
        f"📝 Заданий: {len(tasks)}\n"
        f"👥 Студентов: {len(students)}\n"
        f"🎫 Свободных кодов: {len(codes)}\n\n"
        "**Команды:**\n"
        "/gencodes <N> — создать коды\n"
        "/codes — показать коды\n"
        "/addtopic <id> <n> — тема\n"
        "/addtask — задание\n"
        "/tasks — список заданий\n"
        "/deltask <id> — удалить\n"
        "/students — студенты\n"
    )
    
    await update.message.reply_text(text, parse_mode="Markdown")


# ============== TOPICS WITH BUTTONS ==============

@require_registered
async def topics_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show topics with buttons."""
    user = update.effective_user
    student = db.get_student(user.id)
    student_id = student["id"] if student else None
    
    topics = db.get_topics()
    
    if not topics:
        await update.message.reply_text("Пока нет доступных тем.")
        return
    
    keyboard = []
    for topic in topics:
        tasks = db.get_tasks_by_topic(topic["topic_id"])
        solved = sum(1 for t in tasks if student_id and db.has_solved(student_id, t["task_id"]))
        total = len(tasks)
        
        if total > 0:
            btn_text = f"{topic['name']} ({solved}/{total})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"topic:{topic['topic_id']}")])
    
    if not keyboard:
        await update.message.reply_text("Пока нет заданий.")
        return
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📚 **Выбери тему:**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


# ============== CALLBACK HANDLERS ==============

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
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"📂 **{topic['name']}**\n\nВыбери задание:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
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
    if len(description) > 3000:
        description = description[:3000] + "...\n\n_(сокращено)_"
    
    text = (
        f"📝 **{task['title']}**\n"
        f"ID: `{task_id}`\n\n"
        f"{description}"
    )
    
    keyboard = [
        [InlineKeyboardButton("📤 Отправить решение", callback_data=f"submit:{task_id}")],
        [InlineKeyboardButton("« Назад", callback_data=f"topic:{task['topic_id']}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")


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
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data=f"task:{task_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📤 **{task['title']}**\n\n"
        "Отправь код в следующем сообщении.\n"
        "Можно текстом или файлом `.py`",
        reply_markup=reply_markup,
        parse_mode="Markdown"
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
        
        topics = db.get_topics()
        keyboard = []
        
        for topic in topics:
            tasks = db.get_tasks_by_topic(topic["topic_id"])
            solved = sum(1 for t in tasks if student_id and db.has_solved(student_id, t["task_id"]))
            total = len(tasks)
            
            if total > 0:
                btn_text = f"{topic['name']} ({solved}/{total})"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"topic:{topic['topic_id']}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📚 **Выбери тему:**",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )


# ============== COMMAND: TASK ==============

@require_registered
async def show_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show task description (command version)."""
    if not context.args:
        await update.message.reply_text("Используй: /task <id>\nИли нажми /topics")
        return
    
    task_id = context.args[0]
    task = db.get_task(task_id)
    
    if not task:
        await update.message.reply_text(f"❌ Задание `{task_id}` не найдено.")
        return
    
    text = (
        f"📝 **{task['title']}**\n"
        f"ID: `{task_id}`\n\n"
        f"{task['description']}"
    )
    
    keyboard = [
        [InlineKeyboardButton("📤 Отправить решение", callback_data=f"submit:{task_id}")],
        [InlineKeyboardButton("« К темам", callback_data="back:topics")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


# ============== COMMAND: SUBMIT ==============

@require_registered
async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start submission (command version)."""
    if not context.args:
        await update.message.reply_text("Используй: /submit <id>\nИли кнопку в /topics")
        return
    
    task_id = context.args[0]
    task = db.get_task(task_id)
    
    if not task:
        await update.message.reply_text(f"❌ Задание `{task_id}` не найдено.")
        return
    
    context.user_data["pending_task"] = task_id
    
    await update.message.reply_text(
        f"📤 **{task['title']}**\n\n"
        "Отправь код в следующем сообщении.\n"
        "Можно текстом или файлом `.py`\n\n"
        "Отмена: /cancel",
        parse_mode="Markdown"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation."""
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END


async def handle_code_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle code from student."""
    task_id = context.user_data.get("pending_task")
    if not task_id:
        return
    
    user = update.effective_user
    student = db.get_student(user.id)
    
    if not student and not db.is_admin(user.id):
        await update.message.reply_text("⛔ Сначала зарегистрируйся!")
        return
    
    if not student:
        student = {"id": 0}  # admin testing
    
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
    
    keyboard = []
    if passed:
        keyboard.append([InlineKeyboardButton("🎉 К темам", callback_data="back:topics")])
        result = f"✅ **Задание `{task_id}` выполнено!**\n\n```\n{output[:1500]}\n```"
    else:
        keyboard.append([InlineKeyboardButton("🔄 Ещё раз", callback_data=f"submit:{task_id}")])
        keyboard.append([InlineKeyboardButton("« К заданию", callback_data=f"task:{task_id}")])
        result = f"❌ **Не пройдено**\n\n```\n{output[:1500]}\n```"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await checking.edit_text(result, reply_markup=reply_markup, parse_mode="Markdown")


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
        f"📊 **Твоя статистика**\n\n"
        f"✅ Решено: {stats['solved_tasks']}/{stats['total_tasks']}\n"
        f"📤 Отправок: {stats['total_submissions']}\n"
    )
    
    keyboard = [[InlineKeyboardButton("📚 К заданиям", callback_data="back:topics")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


# ============== MAIN ==============

def main():
    """Start the bot."""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Set BOT_TOKEN!")
        print("   export BOT_TOKEN='your_token'")
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
    
    # Buttons
    app.add_handler(CallbackQueryHandler(topic_callback, pattern="^topic:"))
    app.add_handler(CallbackQueryHandler(task_callback, pattern="^task:"))
    app.add_handler(CallbackQueryHandler(submit_callback, pattern="^submit:"))
    app.add_handler(CallbackQueryHandler(back_callback, pattern="^back:"))
    
    # Code submissions
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code_submission))
    app.add_handler(MessageHandler(filters.Document.FileExtension("py"), handle_code_submission))
    
    print("🤖 Mentor Bot v2 starting...")
    print("   First user becomes admin!")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
