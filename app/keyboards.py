"""Keyboard builders for the bot."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database as db



def main_menu_keyboard(
    is_admin=False, has_assigned=False, can_spin=False, unread_announcements=0
):
    """Build main menu keyboard for students."""
    keyboard = [
        [InlineKeyboardButton("📚 Задания", callback_data="modules:list")],
        [InlineKeyboardButton("🏆 Лидерборд", callback_data="menu:leaderboard")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="menu:mystats")],
    ]
    if has_assigned:
        keyboard.insert(
            1, [InlineKeyboardButton("📌 Назначенные мне", callback_data="myassigned:0")]
        )

    # Announcements with unread badge
    ann_text = "📢 Объявления"
    if unread_announcements > 0:
        ann_text += f" ({unread_announcements} 🔴)"
    keyboard.append([InlineKeyboardButton(ann_text, callback_data="announcements:list")])

    # Meetings
    keyboard.append([InlineKeyboardButton("📅 Мои встречи", callback_data="meetings:my")])

    # Quiz
    keyboard.append(
        [InlineKeyboardButton("❓ Вопросы с собесов", callback_data="quiz:menu")]
    )

    if can_spin:
        keyboard.append(
            [InlineKeyboardButton("🎰 Ежедневная рулетка", callback_data="dailyspin")]
        )
    if is_admin:
        keyboard.append(
            [InlineKeyboardButton("👑 Админ-панель", callback_data="menu:admin")]
        )
    return InlineKeyboardMarkup(keyboard)


def admin_menu_keyboard(admin_user_id=None):
    """Build admin panel keyboard."""
    my_students_count = 0
    if admin_user_id:
        my_students = db.get_mentor_students(admin_user_id)
        my_students_count = len(my_students)

    my_students_text = (
        f"🎓 Мои ученики ({my_students_count})" if my_students_count else "🎓 Мои ученики"
    )

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(my_students_text, callback_data="admin:mystudents")],
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
            [
                InlineKeyboardButton("📢 Объявления", callback_data="admin:announcements"),
                InlineKeyboardButton("📅 Встречи", callback_data="admin:meetings"),
            ],
            [
                InlineKeyboardButton("❓ Вопросы", callback_data="admin:questions"),
            ],
            [InlineKeyboardButton("« Главное меню", callback_data="menu:main")],
        ]
    )


def back_to_menu_keyboard():
    """Keyboard with single 'Back to main menu' button."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("« Главное меню", callback_data="menu:main")]]
    )


def back_to_admin_keyboard():
    """Keyboard with single 'Back to admin panel' button."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("« Админ-панель", callback_data="menu:admin")]]
    )
