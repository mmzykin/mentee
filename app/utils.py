"""Utility functions for the bot."""
from datetime import datetime, timedelta
from typing import Optional

from app.config import MSK


def now_msk() -> datetime:
    """Get current time in Moscow timezone (UTC+3)"""
    return datetime.now(MSK).replace(tzinfo=None)


def to_msk_str(iso_str: str, date_only: bool = False) -> str:
    """Convert ISO timestamp string to MSK display format"""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        dt_msk = dt + timedelta(hours=3)  # UTC -> MSK
        if date_only:
            return dt_msk.strftime("%Y-%m-%d")
        return dt_msk.strftime("%m-%d %H:%M")
    except BaseException:
        return iso_str[:10] if date_only else iso_str[5:16].replace("T", " ")


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def get_raw_text(message) -> str:
    """
    Reconstruct raw text from message, restoring formatting symbols.
    Telegram parses __text__ as underline and removes the underscores.
    This function restores them for code that uses __name__, __init__, etc.
    """
    if not message or not message.text:
        return ""

    text = message.text
    entities = message.entities or []

    if not entities:
        return text

    # Sort entities by offset in reverse order to insert from the end
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)

    result = text
    for entity in sorted_entities:
        start = entity.offset
        end = entity.offset + entity.length

        # Restore underline formatting (__text__)
        if entity.type == "underline":
            result = result[:end] + "__" + result[end:]
            result = result[:start] + "__" + result[start:]
        # Restore italic formatting (_text_ or *text*)
        elif entity.type == "italic":
            result = result[:end] + "_" + result[end:]
            result = result[:start] + "_" + result[start:]
        # Restore bold formatting (*text* or **text**)
        elif entity.type == "bold":
            result = result[:end] + "*" + result[end:]
            result = result[:start] + "*" + result[start:]
        # Restore strikethrough (~~text~~)
        elif entity.type == "strikethrough":
            result = result[:end] + "~~" + result[end:]
            result = result[:start] + "~~" + result[start:]

    return result


async def safe_answer(query, text=None, show_alert=False):
    """Safely answer callback query, ignoring expired queries."""
    try:
        await query.answer(text, show_alert=show_alert)
        return True
    except Exception:
        return False


async def safe_edit(query, text, reply_markup=None, parse_mode="HTML"):
    """Safely edit message, ignoring 'message not modified' errors."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True
    except Exception as e:
        if "not modified" in str(e).lower():
            return True  # Not an error, just nothing changed
        raise


def parse_task_format(text: str) -> Optional[dict]:
    """
    Parse task creation format.
    Returns dict with task_id, topic_id, title, description, test_code, language
    or None if format is invalid.
    
    Expected format:
    TOPIC: topic_id
    TASK_ID: task_id
    TITLE: Task Title
    LANGUAGE: python (optional)
    ---
    ---DESCRIPTION---
    Description text
    ---TESTS---
    test code
    """
    import re
    
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
    except BaseException:
        return None
