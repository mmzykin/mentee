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
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("« Главное меню", callback_data="menu:main")]
    ])


def back_to_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("« Админ-панель", callback_data="menu:admin")]
    ])


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
            await update.message.reply_text(
                f"👑 <b>{name}</b>, ты теперь админ!",
                reply_markup=main_menu_keyboard(is_admin=True),
                parse_mode="HTML"
            )
            return
    if db.get_admin_count() == 0:
        db.add_admin(user.id)
        await update.message.reply_text(
            f"👑 <b>{name}</b>, ты первый — теперь админ!",
            reply_markup=main_menu_keyboard(is_admin=True),
            parse_mode="HTML"
        )
        return
    is_admin = db.is_admin(user.id)
    if is_admin:
        await update.message.reply_text(
            f"👑 <b>{name}</b>!",
            reply_markup=main_menu_keyboard(is_admin=True),
            parse_mode="HTML"
        )
    elif db.get_student(user.id):
        await update.message.reply_text(
            f"👋 <b>{name}</b>!",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"👋 <b>{name}</b>!\n\nРегистрация: /register КОД",
            parse_mode="HTML"
        )


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
        await update.message.reply_text(
            f"✅ Добро пожаловать, <b>{escape_html(user.first_name)}</b>!",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ Неверный код.")


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            await query.edit_message_text("Не зарегистрирован.", reply_markup=back_to_menu_keyboard())
            return
        stats = db.get_student_stats(student["id"])
        text = (
            f"📊 <b>Статистика</b>\n\n"
            f"✅ Решено: <b>{stats['solved_tasks']}</b>/{stats['total_tasks']}\n"
            f"⭐ Бонусы: <b>{stats['bonus_points']}</b>\n"
            f"🎖 Аппрувов: <b>{stats['approved_count']}</b>\n"
            f"📤 Отправок: <b>{stats['total_submissions']}</b>"
        )
        await query.edit_message_text(text, reply_markup=back_to_menu_keyboard(), parse_mode="HTML")
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
    action = query.data.split(":")[1]
    
    if action == "list":
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
    await query.edit_message_text(
        f"📦 <b>{escape_html(module['name'])}</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


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
    await query.edit_message_text(
        f"📚 <b>{escape_html(topic['name'])}</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


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
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отмена", callback_data=f"task:{task_id}")]
    ])
    await query.edit_message_text(
        f"📤 <b>{escape_html(task['title'])}</b>\n\nОтправь код:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


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
        students = db.get_all_students_stats()
        if not students:
            await query.edit_message_text("Нет студентов.", reply_markup=back_to_admin_keyboard())
            return
        keyboard = []
        for s in students:
            name = s.get("first_name") or s.get("username") or "?"
            btn = f"{name}: {s['solved_tasks']}/{s['total_tasks']} +{s['bonus_points']}⭐"
            keyboard.append([InlineKeyboardButton(btn, callback_data=f"student:{s['user_id']}")])
        keyboard.append([InlineKeyboardButton("« Админ", callback_data="menu:admin")])
        await query.edit_message_text("👥 <b>Студенты</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
    elif action == "codes":
        codes = db.get_unused_codes()
        if not codes:
            text = "<i>Нет кодов.</i>"
        else:
            text = f"🎫 <b>Коды</b> ({len(codes)})\n\n"
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
        await query.edit_message_text(
            f"🧹 Удалено кода из <b>{deleted}</b> отправок старше 7 дней.",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="HTML"
        )


async def create_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    action = query.data.split(":")[1]
    
    if action == "module":
        context.user_data["creating"] = "module"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin:modules")]])
        await query.edit_message_text(
            "📦 <b>Новый модуль</b>\n\nОтправь ID и название через пробел:\n<code>2 ООП</code>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    elif action == "topic_select":
        modules = db.get_modules()
        if not modules:
            await query.edit_message_text("Сначала создай модуль.", reply_markup=back_to_admin_keyboard())
            return
        keyboard = []
        for m in modules:
            keyboard.append([InlineKeyboardButton(f"📦 {m['name']}", callback_data=f"create:topic:{m['module_id']}")])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="admin:topics")])
        await query.edit_message_text("Выбери модуль для темы:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif action.startswith("topic:"):
        module_id = action.split(":")[1]
        module = db.get_module(module_id)
        if not module:
            await query.edit_message_text("Модуль не найден.")
            return
        context.user_data["creating"] = "topic"
        context.user_data["module_id"] = module_id
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin:topics")]])
        await query.edit_message_text(
            f"📚 <b>Новая тема в {escape_html(module['name'])}</b>\n\nОтправь ID и название:\n<code>2.1 Классы</code>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    elif action == "task":
        topics = db.get_topics()
        if not topics:
            await query.edit_message_text("Сначала создай тему.", reply_markup=back_to_admin_keyboard())
            return
        context.user_data["creating"] = "task"
        text = "📝 <b>Новое задание</b>\n\nТемы:\n"
        for t in topics:
            text += f"• <code>{t['topic_id']}</code>: {escape_html(t['name'])}\n"
        text += (
            "\nОтправь в формате:\n<code>"
            "TOPIC: topic_id\n"
            "TASK_ID: task_id\n"
            "TITLE: Название\n"
            "---DESCRIPTION---\n"
            "Описание\n"
            "---TESTS---\n"
            "def test(): ...</code>"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin:tasks")]])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        return False
    creating = context.user_data.get("creating")
    if not creating:
        return False
    
    text = update.message.text.strip()
    
    if creating == "module":
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await update.message.reply_text("Формат: <code>id Название</code>", parse_mode="HTML")
            return True
        module_id, name = parts[0], parts[1]
        order = len(db.get_modules()) + 1
        if db.add_module(module_id, name, order):
            del context.user_data["creating"]
            await update.message.reply_text(
                f"✅ Модуль <b>{escape_html(name)}</b> создан!",
                reply_markup=back_to_admin_keyboard(),
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text("❌ ID занят.")
        return True
    
    elif creating == "topic":
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await update.message.reply_text("Формат: <code>id Название</code>", parse_mode="HTML")
            return True
        topic_id, name = parts[0], parts[1]
        module_id = context.user_data.get("module_id", "1")
        order = len(db.get_topics_by_module(module_id)) + 1
        if db.add_topic(topic_id, name, module_id, order):
            del context.user_data["creating"]
            context.user_data.pop("module_id", None)
            await update.message.reply_text(
                f"✅ Тема <b>{escape_html(name)}</b> создана!",
                reply_markup=back_to_admin_keyboard(),
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text("❌ ID занят.")
        return True
    
    elif creating == "task":
        parsed = parse_task_format(text)
        if not parsed:
            await update.message.reply_text("❌ Неверный формат.")
            return True
        topic = db.get_topic(parsed["topic_id"])
        if not topic:
            await update.message.reply_text(f"❌ Тема <code>{parsed['topic_id']}</code> не найдена.", parse_mode="HTML")
            return True
        if db.get_task(parsed["task_id"]):
            await update.message.reply_text("❌ ID занят.")
            return True
        if db.add_task(parsed["task_id"], parsed["topic_id"], parsed["title"], parsed["description"], parsed["test_code"]):
            del context.user_data["creating"]
            await update.message.reply_text(
                f"✅ Задание <b>{escape_html(parsed['title'])}</b> создано!",
                reply_markup=back_to_admin_keyboard(),
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text("❌ Ошибка.")
        return True
    
    return False


async def student_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    name = escape_html(student.get("first_name") or student.get("username") or "?")
    stats = db.get_student_stats(student["id"])
    text = (
        f"📋 <b>{name}</b>\n"
        f"ID: <code>{user_id}</code>\n\n"
        f"✅ {stats['solved_tasks']}/{stats['total_tasks']}\n"
        f"⭐ Бонусов: {stats['bonus_points']}\n"
        f"🎖 Аппрувов: {stats['approved_count']}\n\n"
        "Задания с попытками:"
    )
    keyboard = []
    for topic in db.get_topics():
        for task in db.get_tasks_by_topic(topic["topic_id"]):
            subs = db.get_student_submissions(student["id"], task["task_id"])
            if subs:
                solved = db.has_solved(student["id"], task["task_id"])
                status = "✅" if solved else "❌"
                btn = f"{status} {task['task_id']}: {len(subs)} попыт."
                keyboard.append([InlineKeyboardButton(btn, callback_data=f"attempts:{student['id']}:{task['task_id']}")])
    keyboard.append([InlineKeyboardButton("« Студенты", callback_data="admin:students")])
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
    text = f"📝 <b>{title}</b>\n👤 {name}\n\nПопытки:"
    keyboard = []
    for i, sub in enumerate(subs, 1):
        status = "✅" if sub["passed"] else "❌"
        approved = "⭐" if sub["approved"] else ""
        date = sub["submitted_at"][:16].replace("T", " ") if sub["submitted_at"] else ""
        btn = f"{status}{approved} #{i} {date}"
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
    approved = "⭐ Аппрувнуто" if sub["approved"] else ""
    code = sub["code"] or "[удалён]"
    if len(code) > 3000:
        code = code[:3000] + "\n...(обрезано)"
    text = (
        f"<b>{status} {approved}</b>\n"
        f"Задание: <code>{sub['task_id']}</code>\n"
        f"Время: {sub['submitted_at'][:16]}\n\n"
        f"<pre>{escape_html(code)}</pre>"
    )
    keyboard = []
    if sub["passed"] and not sub["approved"]:
        keyboard.append([InlineKeyboardButton("⭐ Аппрувнуть (+1)", callback_data=f"approve:{sub_id}")])
    elif sub["approved"]:
        keyboard.append([InlineKeyboardButton("❌ Отменить аппрув", callback_data=f"unapprove:{sub_id}")])
    keyboard.append([InlineKeyboardButton("« К попыткам", callback_data=f"attempts:{sub['student_id']}:{sub['task_id']}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    sub_id = int(query.data.split(":")[1])
    if db.approve_submission(sub_id, BONUS_POINTS_PER_APPROVAL):
        await query.answer("⭐ Аппрувнуто!", show_alert=True)
    else:
        await query.answer("Уже или ошибка.", show_alert=True)
    sub = db.get_submission_by_id(sub_id)
    if sub:
        await code_callback(update, context)


async def unapprove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    sub_id = int(query.data.split(":")[1])
    if db.unapprove_submission(sub_id):
        await query.answer("Отменено.", show_alert=True)
    sub = db.get_submission_by_id(sub_id)
    if sub:
        await code_callback(update, context)


async def handle_code_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await handle_admin_text(update, context):
        return
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
    code = None
    if update.message.document:
        if update.message.document.file_name.endswith(".py"):
            file = await update.message.document.get_file()
            data = await file.download_as_bytearray()
            code = data.decode("utf-8")
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
        await update.message.reply_text("❌ Нет кода.")
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
            [InlineKeyboardButton("🎉 К заданиям", callback_data="modules:list")],
            [InlineKeyboardButton("🏆 Лидерборд", callback_data="menu:leaderboard")]
        ])
        result = f"✅ <b>Решено!</b>\n\n<pre>{safe_output}</pre>"
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Ещё", callback_data=f"submit:{task_id}")],
            [InlineKeyboardButton("« Задание", callback_data=f"task:{task_id}")]
        ])
        result = f"❌ <b>Не пройдено</b>\n\n<pre>{safe_output}</pre>"
    await checking.edit_text(result, reply_markup=keyboard, parse_mode="HTML")


@require_admin
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    modules = db.get_modules()
    topics = db.get_topics()
    tasks = db.get_all_tasks()
    text = (
        "👑 <b>Админ</b>\n\n"
        f"📦 Модулей: {len(modules)}\n"
        f"📚 Тем: {len(topics)}\n"
        f"📝 Заданий: {len(tasks)}"
    )
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
    if db.delete_task(context.args[0]):
        await update.message.reply_text("✅ Удалено.")
    else:
        await update.message.reply_text("❌ Не найдено.")


@require_admin
async def del_module_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("<code>/delmodule module_id</code>", parse_mode="HTML")
        return
    if db.delete_module(context.args[0]):
        await update.message.reply_text("✅ Модуль удалён.")
    else:
        await update.message.reply_text("❌ Не найден или есть темы.")


@require_admin
async def del_topic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("<code>/deltopic topic_id</code>", parse_mode="HTML")
        return
    if db.delete_topic(context.args[0]):
        await update.message.reply_text("✅ Тема удалена.")
    else:
        await update.message.reply_text("❌ Не найдена или есть задания.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено.", reply_markup=main_menu_keyboard(db.is_admin(update.effective_user.id)))
    return ConversationHandler.END


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
        solved = 0
        if student_id:
            for t in topics:
                for task in db.get_tasks_by_topic(t["topic_id"]):
                    if db.has_solved(student_id, task["task_id"]):
                        solved += 1
        btn = f"📦 {m['name']} ({solved}/{total})"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"module:{m['module_id']}")])
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
    app.add_handler(CallbackQueryHandler(attempts_callback, pattern="^attempts:"))
    app.add_handler(CallbackQueryHandler(code_callback, pattern="^code:"))
    app.add_handler(CallbackQueryHandler(approve_callback, pattern="^approve:"))
    app.add_handler(CallbackQueryHandler(unapprove_callback, pattern="^unapprove:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code_submission))
    app.add_handler(MessageHandler(filters.Document.FileExtension("py"), handle_code_submission))
    print("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
