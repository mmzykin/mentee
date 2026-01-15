"""Decorators for bot handlers."""
from telegram import Update
from telegram.ext import ContextTypes

import database as db


def require_admin(func):
    """Decorator that restricts handler to admins only."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not db.is_admin(user_id):
            await update.message.reply_text("⛔ Только для администраторов")
            return
        return await func(update, context)

    return wrapper


def require_registered(func):
    """Decorator that restricts handler to registered users (students + admins)."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if db.is_admin(user_id) or db.is_registered(user_id):
            return await func(update, context)
        await update.message.reply_text("⛔ Сначала /register КОД")
        return

    return wrapper
