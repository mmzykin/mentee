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
ADMIN_USERNAMES = ["qwerty1492", "redd_dd"]
BONUS_POINTS_PER_APPROVAL = 1


def main_menu_keyboard(is_admin=False, has_assigned=False, can_spin=False):
    keyboard = [
        [InlineKeyboardButton("📚 Задания", callback_data="modules:list")],
        [InlineKeyboardButton("🏆 Лидерборд", callback_data="menu:leaderboard")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="menu:mystats")],
    ]
    if has_assigned:
        keyboard.insert(1, [InlineKeyboardButton("📌 Назначенные мне", callback_data="myassigned:0")])
    if can_spin:
        keyboard.append([InlineKeyboardButton("🎰 Ежедневная рулетка", callback_data="dailyspin")])
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


async def safe_answer(query, text=None, show_alert=False):
    """Safely answer callback query, ignoring expired queries"""
    try:
        await query.answer(text, show_alert=show_alert)
        return True
    except Exception:
        return False


def parse_task_format(text: str) -> Optional[dict]:
    try:
        topic_match = re.search(r"TOPIC:\s*(\S+)", text)
        task_id_match = re.search(r"TASK_ID:\s*(\S+)", text)
        title_match = re.search(r"TITLE:\s*(.+?)(?:\n|---)", text)
        lang_match = re.search(r"LANGUAGE:\s*(\S+)", text)
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
            "language": lang_match.group(1).strip().lower() if lang_match else "python",
        }
    except:
        return None


def run_python_code_with_tests(code: str, test_code: str) -> tuple[bool, str]:
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


def run_go_code_with_tests(code: str, test_code: str) -> tuple[bool, str]:
    """Run Go code with tests"""
    # Create temp directory for Go module
    temp_dir = tempfile.mkdtemp()
    main_path = os.path.join(temp_dir, "main.go")
    test_path = os.path.join(temp_dir, "main_test.go")
    
    try:
        # Write main code
        with open(main_path, "w", encoding="utf-8") as f:
            f.write(code)
        
        # Write test code
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
        
        # Initialize go module
        subprocess.run(
            ["go", "mod", "init", "solution"],
            cwd=temp_dir, capture_output=True, timeout=5
        )
        
        # Run tests
        result = subprocess.run(
            ["go", "test", "-v", "."],
            cwd=temp_dir, capture_output=True, text=True, timeout=EXEC_TIMEOUT
        )
        
        output = result.stdout + result.stderr
        # Go tests pass if return code is 0 and contains PASS
        passed = result.returncode == 0 and ("PASS" in output or "✅" in output)
        
        # Add checkmark for consistency
        if passed and "✅" not in output:
            output = "✅ Все тесты пройдены!\n\n" + output
        
        return passed, output.strip()
    except subprocess.TimeoutExpired:
        return False, f"⏰ Timeout: {EXEC_TIMEOUT} сек"
    except FileNotFoundError:
        return False, "❌ Go не установлен на сервере"
    except Exception as e:
        return False, f"❌ Ошибка: {e}"
    finally:
        # Cleanup
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


def run_code_with_tests(code: str, test_code: str, language: str = "python") -> tuple[bool, str]:
    """Universal runner - dispatches to language-specific runner"""
    if language == "go":
        return run_go_code_with_tests(code, test_code)
    else:
        return run_python_code_with_tests(code, test_code)


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
    else:
        student = db.get_student(user.id)
        if student:
            has_assigned = len(db.get_assigned_tasks(student["id"])) > 0
            can_spin = db.can_spin_daily(student["id"])
            await update.message.reply_text(f"👋 <b>{name}</b>!", reply_markup=main_menu_keyboard(has_assigned=has_assigned, can_spin=can_spin), parse_mode="HTML")
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
    await safe_answer(query)
    user = update.effective_user
    is_admin = db.is_admin(user.id)
    action = query.data.split(":")[1]
    
    if action == "main":
        has_assigned = False
        can_spin = False
        if not is_admin:
            student = db.get_student(user.id)
            if student:
                has_assigned = len(db.get_assigned_tasks(student["id"])) > 0
                can_spin = db.can_spin_daily(student["id"])
        await query.edit_message_text("🏠 <b>Главное меню</b>", reply_markup=main_menu_keyboard(is_admin, has_assigned, can_spin), parse_mode="HTML")
    elif action == "mystats":
        student = db.get_student(user.id)
        if not student:
            await query.edit_message_text("Не зарегистрирован.", reply_markup=back_to_menu_keyboard())
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
        keyboard = [
            [InlineKeyboardButton("💀 Доска позора", callback_data="menu:shameboard")],
            [InlineKeyboardButton("« Главное меню", callback_data="menu:main")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
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
            [InlineKeyboardButton("« Главное меню", callback_data="menu:main")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
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
    await query.edit_message_text("📚 <b>Модули</b>\n\n🐍 Python  🐹 Go", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def module_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        solved = sum(1 for task in tasks if student_id and db.has_solved(student_id, task["task_id"]))
        total = len(tasks)
        if total > 0:
            btn = f"📚 {t['name']} ({solved}/{total})"
            keyboard.append([InlineKeyboardButton(btn, callback_data=f"topic:{t['topic_id']}")])
    keyboard.append([InlineKeyboardButton("« Модули", callback_data="modules:list")])
    await query.edit_message_text(f"📦 <b>{escape_html(module['name'])}</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await query.edit_message_text(f"📚 <b>{escape_html(topic['name'])}</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def show_task_view(query, context, task_id: str):
    """Helper to display task view"""
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
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Открыть задание", callback_data=f"opentask:{task_id}")],
            [
                InlineKeyboardButton("⏱ +1⭐", callback_data=f"starttimer:{task_id}:0"),
                InlineKeyboardButton("🎰 1→2", callback_data=f"starttimer:{task_id}:1"),
                InlineKeyboardButton("🎰 2→4", callback_data=f"starttimer:{task_id}:2"),
                InlineKeyboardButton("🎰 3→6", callback_data=f"starttimer:{task_id}:3"),
            ],
            [InlineKeyboardButton("« Назад", callback_data=back_target)]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        return
    
    # Show full task
    lang = task.get("language", "python")
    lang_label = "🐹 Go" if lang == "go" else "🐍 Python"
    desc = escape_html(task["description"][:3500])
    text = f"📝 <b>{escape_html(task['title'])}</b>\nID: <code>{task_id}</code> • {lang_label}\n\n<pre>{desc}</pre>"
    
    keyboard_rows = []
    
    if timer_active:
        elapsed = (datetime.now() - timer_info["start_time"]).total_seconds()
        mins, secs = divmod(int(elapsed), 60)
        bet = timer_info.get("bet", 0)
        bet_text = f" (ставка: {bet}⭐)" if bet > 0 else ""
        text += f"\n\n⏱ <b>Таймер: {mins:02d}:{secs:02d}</b>{bet_text}"
        keyboard_rows.append([InlineKeyboardButton("🔄 Сбросить таймер", callback_data=f"resettimer:{task_id}")])
    
    keyboard_rows.append([InlineKeyboardButton("📤 Отправить решение", callback_data=f"submit:{task_id}")])
    keyboard_rows.append([InlineKeyboardButton("« Назад", callback_data=back_target)])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard_rows), parse_mode="HTML")


async def task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    task_id = query.data.split(":")[1]
    await show_task_view(query, context, task_id)


async def opentask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open task in normal mode (no timer allowed)"""
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
    """Start timer for a task with optional bet"""
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
            await safe_answer(query, f"❌ Недостаточно баллов! У тебя: {stats['bonus_points']}⭐", show_alert=True)
            return
        # Deduct bet immediately
        db.add_bonus_points(student["id"], -bet)
    
    bet_text = f" (ставка {bet}⭐)" if bet > 0 else ""
    await safe_answer(query, f"⏱ Таймер запущен!{bet_text}")
    
    # Clear no_timer mode if was set
    context.user_data.pop("no_timer_task", None)
    
    context.user_data["task_timer"] = {
        "task_id": task_id,
        "start_time": datetime.now(),
        "bet": bet
    }
    # Refresh task view to show timer
    await show_task_view(query, context, task_id)


async def resettimer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset timer for a task"""
    query = update.callback_query
    task_id = query.data.split(":")[1]
    
    # Refund bet if timer had a bet
    timer_info = context.user_data.get("task_timer", {})
    if timer_info.get("task_id") == task_id and timer_info.get("bet", 0) > 0:
        user = update.effective_user
        student = db.get_student(user.id)
        if student:
            db.add_bonus_points(student["id"], timer_info["bet"])
        await safe_answer(query, f"⏱ Таймер сброшен! Ставка {timer_info['bet']}⭐ возвращена")
    else:
        await safe_answer(query, "⏱ Таймер сброшен!")
    
    context.user_data.pop("task_timer", None)
    # Refresh task view
    await show_task_view(query, context, task_id)


async def dailyspin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Daily roulette spin"""
    query = update.callback_query
    user = update.effective_user
    student = db.get_student(user.id)
    
    if not student:
        await safe_answer(query, "⛔ Не зарегистрирован")
        return
    
    if not db.can_spin_daily(student["id"]):
        await safe_answer(query, "🎰 Уже крутил сегодня! Приходи завтра", show_alert=True)
        return
    
    await safe_answer(query)
    
    # Spin animation message
    spin_msg = await query.edit_message_text("🎰 <b>Крутим рулетку...</b>\n\n🎡 🎡 🎡", parse_mode="HTML")
    
    import asyncio
    await asyncio.sleep(1)
    
    points = db.do_daily_spin(student["id"])
    
    if points > 0:
        result_text = f"🎉 <b>ВЫИГРЫШ!</b>\n\n+{points}⭐ бонус!"
        emoji = "🎉" * points
    elif points == 0:
        result_text = "😐 <b>Пусто</b>\n\n0 баллов. Повезёт завтра!"
        emoji = "🤷"
    else:
        result_text = f"💀 <b>Неудача!</b>\n\n{points}⭐"
        emoji = "😢"
    
    stats = db.get_student_stats(student["id"])
    result_text += f"\n\nТвой баланс: <b>{stats['bonus_points']}⭐</b>"
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("« Главное меню", callback_data="menu:main")]])
    await spin_msg.edit_text(f"🎰 <b>Рулетка</b>\n\n{emoji}\n\n{result_text}", reply_markup=keyboard, parse_mode="HTML")


async def gamble_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Post-solve gambling - 50/50 to double or lose"""
    query = update.callback_query
    user = update.effective_user
    student = db.get_student(user.id)
    
    if not student:
        await safe_answer(query, "⛔")
        return
    
    amount = int(query.data.split(":")[1])
    stats = db.get_student_stats(student["id"])
    
    if stats["bonus_points"] < amount:
        await safe_answer(query, f"❌ Недостаточно баллов! У тебя: {stats['bonus_points']}⭐", show_alert=True)
        return
    
    await safe_answer(query)
    
    won, new_balance = db.gamble_points(student["id"], amount)
    
    if won:
        result = f"🎉 <b>УДВОИЛ!</b>\n\n+{amount}⭐\nБаланс: <b>{new_balance}⭐</b>"
    else:
        result = f"💀 <b>Проиграл!</b>\n\n-{amount}⭐\nБаланс: <b>{new_balance}⭐</b>"
    
    # Show gamble again if has points
    keyboard_rows = [
        [InlineKeyboardButton("🎉 К заданиям", callback_data="modules:list")],
        [InlineKeyboardButton("🏆 Лидерборд", callback_data="menu:leaderboard")]
    ]
    if new_balance >= 1:
        keyboard_rows.insert(0, [InlineKeyboardButton("🎲 Рискнуть ещё 1⭐", callback_data="gamble:1")])
    if new_balance >= 2:
        keyboard_rows.insert(1, [InlineKeyboardButton("🎲 Рискнуть 2⭐", callback_data="gamble:2")])
    
    keyboard = InlineKeyboardMarkup(keyboard_rows)
    await query.edit_message_text(f"🎲 <b>Рулетка</b>\n\n{result}", reply_markup=keyboard, parse_mode="HTML")


async def submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        elapsed = (datetime.now() - timer_info["start_time"]).total_seconds()
        mins, secs = divmod(int(elapsed), 60)
        timer_text = f"\n⏱ Таймер: <b>{mins:02d}:{secs:02d}</b>"
        if elapsed <= 600:
            timer_text += " (успеваешь на +1⭐!)"
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data=f"task:{task_id}")]])
    await query.edit_message_text(f"📤 <b>{escape_html(task['title'])}</b>{timer_text}\n\nОтправь код:", reply_markup=keyboard, parse_mode="HTML")


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
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
    await safe_answer(query)
    if not db.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔")
        return
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    
    if action == "module":
        context.user_data["creating"] = "module"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin:modules")]])
        await query.edit_message_text(
            "📦 <b>Новый модуль</b>\n\n"
            "Отправь ID, название и язык (опционально):\n"
            "<code>2 ООП</code> — Python по умолчанию\n"
            "<code>go1 Основы Go go</code> — для Go модуля",
            reply_markup=keyboard, parse_mode="HTML"
        )
    
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
        date = sub["submitted_at"][5:16].replace("T", " ") if sub["submitted_at"] else ""
        btn = f"{status}{approved}{feedback} #{sub['id']} {sub['task_id']} {date}"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"code:{sub['id']}")])
    keyboard.append([InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


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
                keyboard.append([InlineKeyboardButton(btn, callback_data=f"attempts:{student_id}:{task['task_id']}")])
    if not keyboard:
        text += "<i>Нет попыток</i>"
    keyboard.append([InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


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
        date = sub["submitted_at"][5:16].replace("T", " ") if sub["submitted_at"] else ""
        btn = f"{status}{approved}{feedback} #{sub['id']} {date}"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"code:{sub['id']}")])
    keyboard.append([InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


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
    text = f"<b>{status}{approved}</b>\nID: <code>#{sub['id']}</code>\nЗадание: <code>{sub['task_id']}</code>\nВремя: {sub['submitted_at'][:16]}\n\n<pre>{escape_html(code)}</pre>"
    if sub.get("feedback"):
        text += f"\n\n💬 <b>Фидбек:</b>\n{escape_html(sub['feedback'])}"
    
    # Show student's current bonus
    student = db.get_student_by_id(sub["student_id"])
    if student:
        bonus = db.get_student_bonus(student["id"])
        text += f"\n\n👤 Баланс студента: <b>{bonus}⭐</b>"
    
    keyboard = []
    row1 = []
    if sub["passed"] and not sub.get("approved") and not is_cheated:
        row1.append(InlineKeyboardButton("⭐ Аппрув", callback_data=f"approve:{sub_id}"))
    elif sub.get("approved"):
        row1.append(InlineKeyboardButton("❌ Убрать аппрув", callback_data=f"unapprove:{sub_id}"))
    row1.append(InlineKeyboardButton("💬 Фидбек", callback_data=f"feedback:{sub_id}"))
    keyboard.append(row1)
    
    # GOD MODE - Cheater punishment (only for passed solutions that aren't already marked)
    if sub["passed"] and not is_cheated:
        keyboard.append([
            InlineKeyboardButton("🚨 Списал!", callback_data=f"cheater:{sub_id}:0"),
            InlineKeyboardButton("🚨 -1⭐", callback_data=f"cheater:{sub_id}:1"),
            InlineKeyboardButton("🚨 -3⭐", callback_data=f"cheater:{sub_id}:3"),
            InlineKeyboardButton("🚨 -5⭐", callback_data=f"cheater:{sub_id}:5"),
        ])
    
    keyboard.append([InlineKeyboardButton("🗑 Удалить", callback_data=f"delsub:{sub_id}")])
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"recent:{sub['student_id']}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await safe_answer(query, "⛔")
        return
    sub_id = int(query.data.split(":")[1])
    sub = db.get_submission_by_id(sub_id)
    if db.approve_submission(sub_id, BONUS_POINTS_PER_APPROVAL):
        await safe_answer(query, "⭐ Аппрувнуто!", show_alert=True)
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


async def cheater_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GOD MODE: Punish cheater - mark as failed and remove points"""
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
                context, student["user_id"],
                f"🚨 <b>Обнаружено списывание!</b>\n\n"
                f"Задание: <b>{escape_html(task_name)}</b>\n"
                f"Решение аннулировано" + (f", штраф: -{penalty}⭐" if penalty > 0 else "")
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
    context.user_data["feedback_for"] = sub_id
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data=f"code:{sub_id}")]])
    await query.edit_message_text(f"💬 Отправь фидбек для попытки #{sub_id}:", reply_markup=keyboard)


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
    keyboard = [[InlineKeyboardButton(f"📦 {m['name']}", callback_data=f"assignmod:{m['module_id']}")] for m in modules]
    assigned = db.get_assigned_tasks(student_id)
    if assigned:
        keyboard.append([InlineKeyboardButton(f"📌 Назначенные ({len(assigned)})", callback_data=f"assigned:{student_id}")])
    keyboard.append([InlineKeyboardButton("« К студенту", callback_data=f"student:{student['user_id']}")])
    name = escape_html(student.get("first_name") or "?")
    await query.edit_message_text(f"📌 Назначить задание для <b>{name}</b>\n\nВыбери модуль:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


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
    student = db.get_student_by_id(student_id)
    topics = db.get_topics_by_module(module_id)
    keyboard = [[InlineKeyboardButton(f"📚 {t['name']}", callback_data=f"assigntopic:{t['topic_id']}")] for t in topics]
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
        keyboard.append([InlineKeyboardButton(f"{prefix}{t['task_id']}: {t['title']}", callback_data=f"toggleassign:{t['task_id']}")])
    topic = db.get_topic(topic_id)
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"assignmod:{topic['module_id']}" if topic else f"assign:{student_id}")])
    await query.edit_message_text("Выбери задание (✅ = уже назначено):", reply_markup=InlineKeyboardMarkup(keyboard))


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
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📝 Открыть задание", callback_data=f"task:{task_id}")]
                ])
                await context.bot.send_message(
                    chat_id=student["user_id"],
                    text=f"📌 <b>Вам назначено новое задание!</b>\n\n"
                         f"<b>{escape_html(task['title'])}</b>\n"
                         f"ID: <code>{task_id}</code>",
                    parse_mode="HTML",
                    reply_markup=keyboard
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
        keyboard.append([InlineKeyboardButton(f"{status} {t['task_id']}: {t['title']}", callback_data=f"unassign:{student_id}:{t['task_id']}")])
    if not assigned:
        text += "<i>Пусто</i>"
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"assign:{student_id}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


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


async def myattempts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Student's own attempts"""
    query = update.callback_query
    await safe_answer(query)
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
    await safe_answer(query)
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
    await safe_answer(query)
    user = update.effective_user
    student = db.get_student(user.id)
    if not student:
        await query.edit_message_text("Не зарегистрирован.", reply_markup=back_to_menu_keyboard())
        return
    
    assigned = db.get_assigned_tasks(student["id"])
    
    if not assigned:
        text = "📌 <b>Назначенные мне задания</b>\n\n<i>Пока ничего не назначено</i>"
        keyboard = [[InlineKeyboardButton("« Главное меню", callback_data="menu:main")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return
    
    text = f"📌 <b>Назначенные мне задания</b> ({len(assigned)})\n\n"
    keyboard = []
    for t in assigned:
        solved = db.has_solved(student["id"], t["task_id"])
        status = "✅" if solved else "⬜"
        btn = f"{status} {t['title']}"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"task:{t['task_id']}")])
    
    keyboard.append([InlineKeyboardButton("« Главное меню", callback_data="menu:main")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def editname_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin edits student name"""
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
        [InlineKeyboardButton("📚 Завершил обучение", callback_data=f"archive:{student_id}:GRADUATED")],
        [InlineKeyboardButton("🚫 Отчислен", callback_data=f"archive:{student_id}:EXPELLED")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"student:{student['user_id']}")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin archives student with reason, asks for feedback"""
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
    """View archived student details"""
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
        await safe_answer(query, "⛔")
        return
    
    student_id = int(query.data.split(":")[1])
    
    # Clear archive fields
    with db.get_db() as conn:
        conn.execute(
            "UPDATE students SET archived_at = NULL, archive_reason = NULL, archive_feedback = NULL WHERE id = ?",
            (student_id,)
        )
    
    await safe_answer(query, "✅ Студент восстановлен!", show_alert=True)
    await query.edit_message_text("✅ Студент восстановлен и снова активен.", reply_markup=back_to_admin_keyboard())


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    
    if db.is_admin(user.id):
        if context.user_data.get("creating") == "module":
            parts = text.split()
            if len(parts) < 2:
                await update.message.reply_text("Формат: <code>id Название [go]</code>", parse_mode="HTML")
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
                await update.message.reply_text(f"✅ Модуль создан! {lang_emoji}", reply_markup=back_to_admin_keyboard())
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
            lang = parsed.get("language", "python")
            if db.add_task(parsed["task_id"], parsed["topic_id"], parsed["title"], parsed["description"], parsed["test_code"], lang):
                del context.user_data["creating"]
                lang_name = "Go 🐹" if lang == "go" else "Python 🐍"
                await update.message.reply_text(f"✅ Задание создано! ({lang_name})", reply_markup=back_to_admin_keyboard())
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
    context.user_data.pop("no_timer_task", None)
    
    # Check timer and bet
    timer_info = context.user_data.get("task_timer", {})
    timer_bonus = False
    timer_text = ""
    bet = 0
    if timer_info.get("task_id") == task_id:
        elapsed = (datetime.now() - timer_info["start_time"]).total_seconds()
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
                    bonus_text = f"\n🎰 <b>+{base_bonus}⭐ выигрыш!</b> (ставка {bet}→{base_bonus})"
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
        stats = db.get_student_stats(student["id"]) if student["id"] != 0 else {"bonus_points": 0}
        keyboard_rows = [
            [InlineKeyboardButton("🎉 К заданиям", callback_data="modules:list")],
            [InlineKeyboardButton("🏆 Лидерборд", callback_data="menu:leaderboard")]
        ]
        if stats["bonus_points"] >= 1:
            keyboard_rows.insert(0, [InlineKeyboardButton("🎲 Рискнуть 1⭐ (50/50)", callback_data="gamble:1")])
        keyboard = InlineKeyboardMarkup(keyboard_rows)
        
        result = f"✅ <b>Решено!</b> (#{sub_id}){timer_text}{bonus_text}{chest_text}\n\n<pre>{safe_output}</pre>"
    else:
        # Reset streak on failure
        if student["id"] != 0:
            db.reset_streak(student["id"])
        
        bet_text = ""
        if bet > 0:
            bet_text = f"\n😢 Ставка {bet}⭐ проиграна"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Ещё", callback_data=f"submit:{task_id}")],
            [InlineKeyboardButton("« Задание", callback_data=f"task:{task_id}")]
        ])
        result = f"❌ <b>Не пройдено</b> (#{sub_id}){timer_text}{bet_text}\n\n<pre>{safe_output}</pre>"
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
        lang_emoji = "🐹" if m.get("language") == "go" else "🐍"
        keyboard.append([InlineKeyboardButton(f"{lang_emoji} {m['name']} ({solved}/{total})", callback_data=f"module:{m['module_id']}")])
    keyboard.append([InlineKeyboardButton("« Меню", callback_data="menu:main")])
    await update.message.reply_text("📚 <b>Модули</b>\n\n🐍 Python  🐹 Go", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


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
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )
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
    app.add_handler(CallbackQueryHandler(opentask_callback, pattern="^opentask:"))
    app.add_handler(CallbackQueryHandler(starttimer_callback, pattern="^starttimer:"))
    app.add_handler(CallbackQueryHandler(resettimer_callback, pattern="^resettimer:"))
    app.add_handler(CallbackQueryHandler(dailyspin_callback, pattern="^dailyspin"))
    app.add_handler(CallbackQueryHandler(gamble_callback, pattern="^gamble:"))
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
    app.add_handler(CallbackQueryHandler(cheater_callback, pattern="^cheater:"))
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
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,  # Игнорировать старые сообщения при старте
    )


if __name__ == "__main__":
    main()