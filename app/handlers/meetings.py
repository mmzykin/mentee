"""Meetings handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from app.keyboards import back_to_admin_keyboard, back_to_menu_keyboard
from app.notifications import notify_mentors
from app.utils import escape_html, safe_answer, to_msk_str


async def meetings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    student = db.get_student(user.id)
    is_admin = db.is_admin(user.id)

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "my"

    if action == "my":
        if not student:
            await query.edit_message_text(
                "⛔ Нужна регистрация", reply_markup=back_to_menu_keyboard()
            )
            return

        meetings = db.get_meetings(student_id=student["id"], include_past=False)
        text = "📅 <b>Мои встречи</b>\n\n"

        if meetings:
            for m in meetings:
                status_emoji = {
                    "pending": "⏳",
                    "confirmed": "✅",
                    "cancelled": "❌",
                    "requested": "🔔",
                    "slot_requested": "🕐",
                }.get(m["status"], "⏳")
                text += f"{status_emoji} <b>{escape_html(m['title'])}</b>\n"

                # Show time slot or confirmed time
                if (
                    m["status"] == "slot_requested"
                    and m.get("time_slot_start")
                    and m.get("time_slot_end")
                ):
                    date_str = m["time_slot_start"][:10]
                    slot_start = m["time_slot_start"][11:16]
                    slot_end = m["time_slot_end"][11:16]
                    text += f"   📅 {date_str}\n"
                    text += (
                        f"   🕐 Интервал: {slot_start} — {slot_end} ({m['duration_minutes']} мин)\n"
                    )
                    text += f"   <i>Ожидание выбора времени ментором</i>\n"
                elif m.get("confirmed_time"):
                    dt = to_msk_str(m["confirmed_time"])
                    text += f"   🕐 {dt} ({m['duration_minutes']} мин)\n"
                else:
                    dt = to_msk_str(m["scheduled_at"])
                    text += f"   🕐 {dt} ({m['duration_minutes']} мин)\n"

                if m["meeting_link"]:
                    text += f"   🔗 <a href='{m['meeting_link']}'>Открыть Телемост</a>\n"
                text += "\n"
        else:
            text += "<i>Нет запланированных встреч</i>\n"

        keyboard = [
            [InlineKeyboardButton("➕ Запросить встречу", callback_data="meetings:request")],
            [InlineKeyboardButton("« Главное меню", callback_data="menu:main")],
        ]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    elif action == "request":
        if not student:
            await query.edit_message_text(
                "⛔ Нужна регистрация", reply_markup=back_to_menu_keyboard()
            )
            return
        context.user_data["creating"] = "meeting_request"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="meetings:my")]]
        )
        await query.edit_message_text(
            "📅 <b>Запрос встречи с ментором</b>\n\n"
            "Отправь в формате:\n"
            "<code>Тема встречи\n"
            "2026-01-20\n"
            "16:00-21:00\n"
            "30</code>\n\n"
            "Строки:\n"
            "1. Тема/цель встречи\n"
            "2. Дата (YYYY-MM-DD)\n"
            "3. Временной интервал (HH:MM-HH:MM) — когда вам удобно\n"
            "4. Длительность в минутах\n\n"
            "💡 <i>Пример: могу завтра с 16:00 до 21:00 — "
            "ментор выберет удобное ему время</i>",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    elif action == "all" and is_admin:
        meetings = db.get_meetings(include_past=True)
        text = "📅 <b>Все встречи</b>\n\n"

        if meetings:
            for m in meetings[:15]:
                student_obj = db.get_student_by_id(m["student_id"]) if m["student_id"] else None
                student_name = (
                    (student_obj.get("first_name") or student_obj.get("username") or "?")
                    if student_obj
                    else "—"
                )
                status_emoji = {
                    "pending": "⏳",
                    "confirmed": "✅",
                    "cancelled": "❌",
                    "slot_requested": "🕐",
                }.get(m["status"], "⏳")
                text += f"{status_emoji} <b>{escape_html(m['title'])}</b>\n"

                # Show appropriate time info
                if m["status"] == "slot_requested" and m.get("time_slot_start"):
                    date_str = m["time_slot_start"][:10]
                    slot_start = m["time_slot_start"][11:16]
                    slot_end = m["time_slot_end"][11:16] if m.get("time_slot_end") else "—"
                    text += f"   👤 {student_name} | 📅 {date_str} {slot_start}-{slot_end}\n\n"
                elif m.get("confirmed_time"):
                    dt = to_msk_str(m["confirmed_time"])
                    text += f"   👤 {student_name} | 🕐 {dt}\n\n"
                else:
                    dt = to_msk_str(m["scheduled_at"])
                    text += f"   👤 {student_name} | 🕐 {dt}\n\n"
        else:
            text += "<i>Нет встреч</i>\n"

        keyboard = [[InlineKeyboardButton("« Админ", callback_data="admin:meetings")]]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    elif action == "links" and is_admin:
        # Show links to upcoming meetings
        meetings = db.get_meetings(include_past=False)
        meetings_with_links = [
            m for m in meetings if m.get("meeting_link") and m["status"] != "cancelled"
        ]

        text = "🔗 <b>Ссылки на встречи</b>\n\n"

        if meetings_with_links:
            for m in meetings_with_links:
                student_obj = db.get_student_by_id(m["student_id"]) if m["student_id"] else None
                student_name = (
                    (student_obj.get("first_name") or student_obj.get("username") or "?")
                    if student_obj
                    else "—"
                )
                dt = to_msk_str(m["scheduled_at"])
                status_emoji = {"pending": "⏳", "confirmed": "✅"}.get(m["status"], "⏳")

                text += f"{status_emoji} <b>{escape_html(m['title'])}</b>\n"
                text += f"👤 {student_name} | 🕐 {dt}\n"
                text += f"🔗 <a href='{m['meeting_link']}'>{m['meeting_link']}</a>\n\n"
        else:
            text += "<i>Нет встреч со ссылками</i>\n"

        keyboard = [[InlineKeyboardButton("« Встречи", callback_data="admin:meetings")]]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )


async def meeting_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user

    parts = query.data.split(":")
    action = parts[0]  # meeting_confirm or meeting_decline
    meeting_id = int(parts[1])

    meeting = db.get_meeting(meeting_id)
    if not meeting:
        await query.edit_message_text("Встреча не найдена.")
        return

    if action == "meeting_confirm":
        db.update_meeting_status(meeting_id, "confirmed")
        await query.edit_message_text(
            f"✅ <b>Встреча подтверждена!</b>\n\n"
            f"<b>{escape_html(meeting['title'])}</b>\n"
            f"🕐 {to_msk_str(meeting['scheduled_at'])}\n"
            f"🔗 <a href='{meeting['meeting_link']}'>Открыть Телемост</a>\n\n"
            f"Напоминание придёт за 24 часа и за 1 час до встречи.",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    elif action == "meeting_decline":
        db.update_meeting_status(meeting_id, "cancelled")
        await query.edit_message_text(
            f"❌ <b>Встреча отклонена</b>\n\n"
            f"Свяжитесь с ментором для выбора другого времени.",
            parse_mode="HTML",
        )
    elif action == "meeting_approve":
        # Admin approving a student's meeting request
        if not db.is_admin(user.id):
            await query.edit_message_text("⛔ Только для админов")
            return

        context.user_data["creating"] = "meeting_approve"
        context.user_data["approve_meeting_id"] = meeting_id

        student_obj = db.get_student_by_id(meeting["student_id"]) if meeting["student_id"] else None
        student_name = (
            (student_obj.get("first_name") or student_obj.get("username") or "?")
            if student_obj
            else "—"
        )
        dt = to_msk_str(meeting["scheduled_at"])

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="admin:meetings")]]
        )
        await query.edit_message_text(
            f"✅ <b>Подтверждение встречи</b>\n\n"
            f"👤 {student_name}\n"
            f"📋 {escape_html(meeting['title'])}\n"
            f"🕐 {dt}\n"
            f"⏱ {meeting['duration_minutes']} мин\n\n"
            f"<b>Отправь ссылку на Яндекс.Телемост:</b>",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    elif action == "meeting_reject":
        # Admin rejecting a student's meeting request
        if not db.is_admin(user.id):
            await query.edit_message_text("⛔ Только для админов")
            return

        db.update_meeting_status(meeting_id, "cancelled")

        # Notify student
        if meeting["student_id"]:
            student_obj = db.get_student_by_id(meeting["student_id"])
            if student_obj:
                try:
                    await context.bot.send_message(
                        student_obj["user_id"],
                        f"❌ <b>Запрос на встречу отклонён</b>\n\n"
                        f"📋 {escape_html(meeting['title'])}\n\n"
                        f"Попробуй выбрать другое время.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        await query.edit_message_text(
            f"❌ Запрос отклонён.\n\nСтудент уведомлён.", reply_markup=back_to_admin_keyboard()
        )


async def meeting_slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available times within a slot for mentor to choose."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user

    if not db.is_admin(user.id):
        await query.edit_message_text("⛔ Только для админов/менторов")
        return

    parts = query.data.split(":")
    meeting_id = int(parts[1])

    meeting = db.get_meeting(meeting_id)
    if not meeting:
        await query.edit_message_text("Встреча не найдена.")
        return

    # Get available times
    times = db.get_meeting_slot_times(meeting_id)
    if not times:
        await query.edit_message_text("❌ Не удалось получить доступные времена")
        return

    # Create buttons for each available time (3 per row)
    buttons = []
    row = []
    for t in times:
        row.append(InlineKeyboardButton(t, callback_data=f"meeting_slot_time:{meeting_id}:{t}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="admin:meetings")])

    student_obj = db.get_student_by_id(meeting["student_id"]) if meeting["student_id"] else None
    student_name = (
        (student_obj.get("first_name") or student_obj.get("username") or "?")
        if student_obj
        else "—"
    )

    # Format date from time_slot_start
    date_str = meeting["time_slot_start"][:10] if meeting.get("time_slot_start") else "—"
    slot_start = meeting["time_slot_start"][11:16] if meeting.get("time_slot_start") else "—"
    slot_end = meeting["time_slot_end"][11:16] if meeting.get("time_slot_end") else "—"

    await query.edit_message_text(
        f"🕐 <b>Выберите время для встречи</b>\n\n"
        f"👤 {escape_html(student_name)}\n"
        f"📋 {escape_html(meeting['title'])}\n"
        f"📅 Дата: {date_str}\n"
        f"⏱ {meeting['duration_minutes']} мин\n"
        f"🕐 Удобно студенту: {slot_start} — {slot_end}\n\n"
        f"<b>Выберите время начала:</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def meeting_slot_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle time selection from slot - ask for meeting link."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user

    if not db.is_admin(user.id):
        await query.edit_message_text("⛔ Только для админов/менторов")
        return

    parts = query.data.split(":")
    meeting_id = int(parts[1])
    selected_time = ":".join(parts[2:])  # time contains ":"

    meeting = db.get_meeting(meeting_id)
    if not meeting:
        await query.edit_message_text("Встреча не найдена.")
        return

    # Store selection and ask for link
    context.user_data["creating"] = "meeting_slot_link"
    context.user_data["slot_meeting_id"] = meeting_id
    context.user_data["slot_selected_time"] = selected_time

    student_obj = db.get_student_by_id(meeting["student_id"]) if meeting["student_id"] else None
    student_name = (
        (student_obj.get("first_name") or student_obj.get("username") or "?")
        if student_obj
        else "—"
    )

    date_str = meeting["time_slot_start"][:10] if meeting.get("time_slot_start") else "—"

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Отмена", callback_data="admin:meetings")]]
    )

    await query.edit_message_text(
        f"✅ <b>Время выбрано: {selected_time}</b>\n\n"
        f"👤 {escape_html(student_name)}\n"
        f"📋 {escape_html(meeting['title'])}\n"
        f"📅 {date_str} {selected_time}\n"
        f"⏱ {meeting['duration_minutes']} мин\n\n"
        f"<b>Отправьте ссылку на Телемост:</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def meeting_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle duration selection for admin meeting creation."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user

    if not db.is_admin(user.id):
        await query.edit_message_text("⛔ Только для админов")
        return

    parts = query.data.split(":")
    duration = int(parts[1])

    meeting_data = context.user_data.get("meeting_data")
    if not meeting_data:
        await query.edit_message_text(
            "❌ Данные встречи не найдены", reply_markup=back_to_admin_keyboard()
        )
        return

    student_id = context.user_data.get("meeting_student_id")
    meeting_id = db.create_meeting(
        student_id,
        meeting_data["title"],
        meeting_data["link"],
        meeting_data["scheduled_at"],
        duration,
        user.id,
    )

    # Clear context
    context.user_data.pop("creating", None)
    context.user_data.pop("meeting_data", None)
    context.user_data.pop("meeting_student_id", None)

    # Notify student
    if student_id:
        student = db.get_student_by_id(student_id)
        if student:
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Подтвердить", callback_data=f"meeting_confirm:{meeting_id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Отклонить", callback_data=f"meeting_decline:{meeting_id}"
                        )
                    ],
                ]
            )
            try:
                await context.bot.send_message(
                    student["user_id"],
                    f"📅 <b>Назначена встреча!</b>\n\n"
                    f"<b>{escape_html(meeting_data['title'])}</b>\n"
                    f"🕐 {meeting_data['dt_str']}\n"
                    f"⏱ {duration} мин\n\n"
                    f"🔗 <a href='{meeting_data['link']}'>Открыть в Телемосте</a>",
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            except Exception:
                pass

    await query.edit_message_text(
        f"✅ Встреча создана!\n\n"
        f"📅 {escape_html(meeting_data['title'])}\n🕐 {meeting_data['dt_str']}\n⏱ {duration} мин",
        reply_markup=back_to_admin_keyboard(),
        parse_mode="HTML",
    )


async def meeting_request_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle duration selection for student meeting request."""
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    student = db.get_student(user.id)

    if not student:
        await query.edit_message_text("⛔ Нужна регистрация", reply_markup=back_to_menu_keyboard())
        return

    parts = query.data.split(":")
    duration = int(parts[1])

    request_data = context.user_data.get("meeting_request_data")
    if not request_data:
        await query.edit_message_text(
            "❌ Данные запроса не найдены", reply_markup=back_to_menu_keyboard()
        )
        return

    # Create meeting request (no link yet, status = requested)
    meeting_id = db.create_meeting(
        student["id"],
        request_data["title"],
        "",
        request_data["scheduled_at"],
        duration,
        student["user_id"],
    )
    with db.get_db() as conn:
        conn.execute("UPDATE meetings SET status = 'requested' WHERE id = ?", (meeting_id,))

    # Clear context
    context.user_data.pop("creating", None)
    context.user_data.pop("meeting_request_data", None)

    # Notify assigned mentors (or all admins as fallback)
    student_name = student.get("first_name") or student.get("username") or "?"

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Подтвердить", callback_data=f"meeting_approve:{meeting_id}")],
            [InlineKeyboardButton("❌ Отклонить", callback_data=f"meeting_reject:{meeting_id}")],
        ]
    )

    await notify_mentors(
        context,
        student["id"],
        f"🔔 <b>Запрос на встречу!</b>\n\n"
        f"👤 От: <b>{escape_html(student_name)}</b>\n"
        f"📋 Тема: <b>{escape_html(request_data['title'])}</b>\n"
        f"🕐 Время: {request_data['dt_str']}\n"
        f"⏱ {duration} мин",
        keyboard=keyboard,
    )

    await query.edit_message_text(
        f"✅ Запрос отправлен ментору!\n\n"
        f"📋 {escape_html(request_data['title'])}\n🕐 {request_data['dt_str']}\n⏱ {duration} мин\n\n"
        f"Ожидай подтверждения.",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
