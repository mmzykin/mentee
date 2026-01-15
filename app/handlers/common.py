"""Common handlers: start, help, register, cancel, topics, leaderboard."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from app.config import ADMIN_USERNAMES
from app.utils import escape_html
from app.keyboards import main_menu_keyboard, back_to_menu_keyboard
from app.decorators import require_registered


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    name = escape_html(user.first_name)
    admin_name = user.first_name or user.username or str(user.id)
    
    if user.username and user.username.lower() in ADMIN_USERNAMES:
        if not db.is_admin(user.id):
            db.add_admin(user.id, admin_name)
            await update.message.reply_text(
                f"👑 <b>{name}</b>, ты теперь админ!",
                reply_markup=main_menu_keyboard(is_admin=True),
                parse_mode="HTML",
            )
            return
        else:
            # Update name for existing admin
            db.update_admin_name(user.id, admin_name)
    
    if db.get_admin_count() == 0:
        db.add_admin(user.id, admin_name)
        await update.message.reply_text(
            f"👑 <b>{name}</b>, ты первый — теперь админ!",
            reply_markup=main_menu_keyboard(is_admin=True),
            parse_mode="HTML",
        )
        return
    
    is_admin = db.is_admin(user.id)
    if is_admin:
        await update.message.reply_text(
            f"👑 <b>{name}</b>!", reply_markup=main_menu_keyboard(is_admin=True), parse_mode="HTML"
        )
    else:
        student = db.get_student(user.id)
        if student:
            has_assigned = len(db.get_assigned_tasks(student["id"])) > 0
            can_spin = db.can_spin_daily(student["id"])
            await update.message.reply_text(
                f"👋 <b>{name}</b>!",
                reply_markup=main_menu_keyboard(has_assigned=has_assigned, can_spin=can_spin),
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"👋 <b>{name}</b>!\n\nРегистрация: /register КОД", parse_mode="HTML"
            )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    is_admin = db.is_admin(update.effective_user.id)
    text = (
        "📖 <b>Команды</b>\n\n/start — меню\n"
        "/topics — задания\n/leaderboard — рейтинг"
    )
    if is_admin:
        text += "\n\n👑 <b>Админ</b>\n/admin — панель\n/gencodes N — коды"
    await update.message.reply_text(
        text, reply_markup=main_menu_keyboard(is_admin), parse_mode="HTML"
    )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /register command."""
    user = update.effective_user
    if db.is_registered(user.id):
        await update.message.reply_text(
            "✅ Уже зарегистрирован!", reply_markup=main_menu_keyboard()
        )
        return
    if not context.args:
        await update.message.reply_text("Используй: <code>/register КОД</code>", parse_mode="HTML")
        return
    if db.register_student(user.id, user.username or "", user.first_name or "", context.args[0]):
        await update.message.reply_text(
            f"✅ Добро пожаловать, <b>{escape_html(user.first_name)}</b>!",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("❌ Неверный код.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command."""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Отменено.", reply_markup=main_menu_keyboard(db.is_admin(update.effective_user.id))
    )


@require_registered
async def topics_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /topics command - show modules list."""
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
        solved = sum(
            1
            for t in topics
            for task in db.get_tasks_by_topic(t["topic_id"])
            if student_id and db.has_solved(student_id, task["task_id"])
        )
        lang_emoji = "🐹" if m.get("language") == "go" else "🐍"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{lang_emoji} {m['name']} ({solved}/{total})",
                    callback_data=f"module:{m['module_id']}",
                )
            ]
        )
    keyboard.append([InlineKeyboardButton("« Меню", callback_data="menu:main")])
    await update.message.reply_text(
        "📚 <b>Модули</b>\n\n🐍 Python  🐹 Go",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


@require_registered
async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /leaderboard command."""
    leaders = db.get_leaderboard(15)
    if not leaders:
        await update.message.reply_text("Пусто.", reply_markup=back_to_menu_keyboard())
        return
    
    text = "🏆 <b>Лидерборд</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for l in leaders:
        name = escape_html(l.get("first_name") or l.get("username") or "???")
        medal = medals[l["rank"] - 1] if l["rank"] <= 3 else f"{l['rank']}."
        text += f"{medal} <b>{name}</b> — {l['solved']}✅"
        if l["bonus_points"] > 0:
            text += f" +{l['bonus_points']}⭐"
        text += f" = <b>{l['score']}</b>\n"
    await update.message.reply_text(text, reply_markup=back_to_menu_keyboard(), parse_mode="HTML")
