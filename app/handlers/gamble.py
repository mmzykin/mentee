"""Gambling handlers - daily spin and gamble."""
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from app.utils import safe_answer


async def dailyspin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Daily roulette spin."""
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
    spin_msg = await query.edit_message_text(
        "🎰 <b>Крутим рулетку...</b>\n\n🎡 🎡 🎡", parse_mode="HTML"
    )

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

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("« Главное меню", callback_data="menu:main")]]
    )
    await spin_msg.edit_text(
        f"🎰 <b>Рулетка</b>\n\n{emoji}\n\n{result_text}", reply_markup=keyboard, parse_mode="HTML"
    )


async def gamble_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Post-solve gambling - 50/50 to double or lose."""
    query = update.callback_query
    user = update.effective_user
    student = db.get_student(user.id)

    if not student:
        await safe_answer(query, "⛔")
        return

    amount = int(query.data.split(":")[1])
    stats = db.get_student_stats(student["id"])

    if stats["bonus_points"] < amount:
        await safe_answer(
            query, f"❌ Недостаточно баллов! У тебя: {stats['bonus_points']}⭐", show_alert=True
        )
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
        [InlineKeyboardButton("🏆 Лидерборд", callback_data="menu:leaderboard")],
    ]
    if new_balance >= 1:
        keyboard_rows.insert(
            0, [InlineKeyboardButton("🎲 Рискнуть ещё 1⭐", callback_data="gamble:1")]
        )
    if new_balance >= 2:
        keyboard_rows.insert(1, [InlineKeyboardButton("🎲 Рискнуть 2⭐", callback_data="gamble:2")])

    keyboard = InlineKeyboardMarkup(keyboard_rows)
    await query.edit_message_text(
        f"🎲 <b>Рулетка</b>\n\n{result}", reply_markup=keyboard, parse_mode="HTML"
    )
