"""
Tests for bot.py handlers with mocked Telegram API.
All Telegram interactions are mocked, database uses temp SQLite.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import database as db
from tests.conftest import (
    MockUser, MockMessage, MockUpdate, MockContext, MockCallbackQuery,
    create_registered_student, create_admin, create_task_with_topic
)


# ============= UTILITY FUNCTION TESTS =============

class TestUtilityFunctions:
    """Tests for utility functions in bot.py."""
    
    def test_escape_html(self, clean_db):
        """Test HTML escaping."""
        from bot import escape_html
        assert escape_html("<script>") == "&lt;script&gt;"
        assert escape_html("&test") == "&amp;test"
        assert escape_html("normal") == "normal"
    
    def test_get_raw_text_no_entities(self, clean_db):
        """Test get_raw_text with no entities."""
        from bot import get_raw_text
        message = MockMessage(text="Hello world")
        result = get_raw_text(message)
        assert result == "Hello world"
    
    def test_get_raw_text_with_underline(self, clean_db):
        """Test get_raw_text restores underlines."""
        from bot import get_raw_text
        
        class Entity:
            def __init__(self, type, offset, length):
                self.type = type
                self.offset = offset
                self.length = length
        
        message = MockMessage(text="def name():", entities=[
            Entity("underline", 4, 4)  # "name" was __name__
        ])
        result = get_raw_text(message)
        assert "__name__" in result
    
    def test_to_msk_str(self, clean_db):
        """Test ISO to MSK string conversion."""
        from bot import to_msk_str
        result = to_msk_str("2025-06-15T12:00:00")
        assert "15" in result  # Should contain day
    
    def test_to_msk_str_empty(self, clean_db):
        """Test to_msk_str with empty string."""
        from bot import to_msk_str
        assert to_msk_str("") == ""
        assert to_msk_str(None) == ""


class TestParseTaskFormat:
    """Tests for task format parsing."""
    
    def test_parse_valid_task(self, clean_db):
        """Test parsing valid task format."""
        from bot import parse_task_format
        text = """TOPIC: variables
TASK_ID: var_1
TITLE: Create Variable
---
---DESCRIPTION---
Create a variable x = 10
---TESTS---
assert x == 10
print('✅')"""
        result = parse_task_format(text)
        assert result is not None
        assert result['topic_id'] == 'variables'
        assert result['task_id'] == 'var_1'
        assert result['title'] == 'Create Variable'
    
    def test_parse_invalid_task(self, clean_db):
        """Test parsing invalid task format."""
        from bot import parse_task_format
        result = parse_task_format("random text")
        assert result is None


# ============= KEYBOARD FUNCTION TESTS =============

class TestKeyboardFunctions:
    """Tests for keyboard generation functions."""
    
    def test_main_menu_keyboard_student(self, clean_db):
        """Test main menu for regular student."""
        from bot import main_menu_keyboard
        kb = main_menu_keyboard(is_admin=False)
        assert kb is not None
        # Should not have admin button
        buttons = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "👑 Админ-панель" not in buttons
    
    def test_main_menu_keyboard_admin(self, clean_db):
        """Test main menu for admin."""
        from bot import main_menu_keyboard
        kb = main_menu_keyboard(is_admin=True)
        buttons = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "👑 Админ-панель" in buttons
    
    def test_main_menu_with_assigned(self, clean_db):
        """Test main menu shows assigned tasks button."""
        from bot import main_menu_keyboard
        kb = main_menu_keyboard(has_assigned=True)
        buttons = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "📌 Назначенные мне" in buttons
    
    def test_main_menu_with_spin(self, clean_db):
        """Test main menu shows daily spin when available."""
        from bot import main_menu_keyboard
        kb = main_menu_keyboard(can_spin=True)
        buttons = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "🎰 Ежедневная рулетка" in buttons
    
    def test_main_menu_unread_announcements(self, clean_db):
        """Test main menu shows unread announcement count."""
        from bot import main_menu_keyboard
        kb = main_menu_keyboard(unread_announcements=5)
        buttons = [btn.text for row in kb.inline_keyboard for btn in row]
        ann_btn = [b for b in buttons if "Объявления" in b][0]
        assert "(5 🔴)" in ann_btn
    
    def test_admin_menu_keyboard(self, clean_db):
        """Test admin menu keyboard."""
        from bot import admin_menu_keyboard
        kb = admin_menu_keyboard()
        buttons = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "📦 Модули" in buttons
        assert "📚 Темы" in buttons
        assert "👥 Студенты" in buttons
    
    def test_back_to_menu_keyboard(self, clean_db):
        """Test back to menu keyboard."""
        from bot import back_to_menu_keyboard
        kb = back_to_menu_keyboard()
        assert len(kb.inline_keyboard) == 1
        assert kb.inline_keyboard[0][0].callback_data == "menu:main"


# ============= COMMAND HANDLER TESTS =============

class TestStartCommand:
    """Tests for /start command handler."""
    
    @pytest.mark.asyncio
    async def test_start_new_user(self, clean_db):
        """Test /start for unregistered user (not first user, so not auto-admin)."""
        from bot import start
        
        # Create an admin first so new user won't become admin
        create_admin(111111)
        
        user = MockUser(id=999999, username="newuser", first_name="New")
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        await start(update, context)
        
        message.reply_text.assert_called_once()
        call_args = message.reply_text.call_args
        assert "/register" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_start_registered_student(self, clean_db):
        """Test /start for registered student."""
        from bot import start
        
        student = create_registered_student(111111, "testuser", "Test")
        
        user = MockUser(id=111111, username="testuser", first_name="Test")
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        await start(update, context)
        
        message.reply_text.assert_called_once()
        call_args = message.reply_text.call_args
        # Should greet by name
        assert "Test" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_start_first_admin(self, clean_db):
        """Test /start when no admins exist makes user admin."""
        from bot import start
        
        # Ensure no admins exist
        assert db.get_admin_count() == 0
        
        user = MockUser(id=555555, username="firstuser", first_name="First")
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        await start(update, context)
        
        assert db.is_admin(555555) is True
        message.reply_text.assert_called_once()
        call_args = message.reply_text.call_args
        assert "админ" in call_args[0][0].lower()


class TestRegisterCommand:
    """Tests for /register command handler."""
    
    @pytest.mark.asyncio
    async def test_register_no_code(self, clean_db):
        """Test /register without code."""
        from bot import register
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext(args=[])
        
        await register(update, context)
        
        message.reply_text.assert_called_once()
        assert "КОД" in message.reply_text.call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_register_invalid_code(self, clean_db):
        """Test /register with invalid code."""
        from bot import register
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext(args=["INVALID"])
        
        await register(update, context)
        
        call_text = message.reply_text.call_args[0][0]
        assert "Неверный" in call_text
    
    @pytest.mark.asyncio
    async def test_register_valid_code(self, clean_db):
        """Test /register with valid code."""
        from bot import register
        
        codes = db.create_codes(1)
        
        user = MockUser(id=111111, username="newstudent", first_name="New")
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext(args=[codes[0]])
        
        await register(update, context)
        
        call_text = message.reply_text.call_args[0][0]
        assert "Добро пожаловать" in call_text
        assert db.is_registered(111111) is True
    
    @pytest.mark.asyncio
    async def test_register_already_registered(self, clean_db):
        """Test /register when already registered."""
        from bot import register
        
        create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext(args=["ANYCODE"])
        
        await register(update, context)
        
        call_text = message.reply_text.call_args[0][0]
        assert "Уже зарегистрирован" in call_text


class TestHelpCommand:
    """Tests for /help command handler."""
    
    @pytest.mark.asyncio
    async def test_help_student(self, clean_db):
        """Test /help for student."""
        from bot import help_cmd
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        await help_cmd(update, context)
        
        message.reply_text.assert_called_once()
        call_text = message.reply_text.call_args[0][0]
        assert "/start" in call_text
        assert "/topics" in call_text
    
    @pytest.mark.asyncio
    async def test_help_admin(self, clean_db):
        """Test /help for admin."""
        from bot import help_cmd
        
        create_admin(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        await help_cmd(update, context)
        
        call_text = message.reply_text.call_args[0][0]
        assert "Админ" in call_text
        assert "/gencodes" in call_text


# ============= SAFE HELPER TESTS =============

class TestSafeHelpers:
    """Tests for safe_answer and safe_edit helpers."""
    
    @pytest.mark.asyncio
    async def test_safe_answer_success(self, clean_db):
        """Test safe_answer succeeds."""
        from bot import safe_answer
        
        query = MockCallbackQuery()
        result = await safe_answer(query, "OK")
        assert result is True
        query.answer.assert_called_once_with("OK", show_alert=False)
    
    @pytest.mark.asyncio
    async def test_safe_answer_expired(self, clean_db):
        """Test safe_answer handles expired query."""
        from bot import safe_answer
        
        query = MockCallbackQuery()
        query.answer.side_effect = Exception("Query expired")
        
        result = await safe_answer(query, "OK")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_safe_edit_success(self, clean_db):
        """Test safe_edit succeeds."""
        from bot import safe_edit
        
        query = MockCallbackQuery()
        result = await safe_edit(query, "New text")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_safe_edit_not_modified(self, clean_db):
        """Test safe_edit handles 'not modified' gracefully."""
        from bot import safe_edit
        
        query = MockCallbackQuery()
        query.edit_message_text.side_effect = Exception("Message is not modified")
        
        result = await safe_edit(query, "Same text")
        assert result is True  # Not an error


# ============= CALLBACK HANDLER TESTS =============

class TestMenuCallback:
    """Tests for menu callback handler."""
    
    @pytest.mark.asyncio
    async def test_menu_main(self, clean_db):
        """Test returning to main menu."""
        from bot import menu_callback
        
        student = create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="menu:main", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await menu_callback(update, context)
        
        query.answer.assert_called()
    
    @pytest.mark.asyncio
    async def test_menu_mystats(self, clean_db):
        """Test viewing own stats."""
        from bot import menu_callback
        
        student = create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="menu:mystats", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await menu_callback(update, context)
        
        query.answer.assert_called()
        # Should show stats
        call_text = query.edit_message_text.call_args[0][0]
        assert "статистика" in call_text.lower()
    
    @pytest.mark.asyncio
    async def test_menu_leaderboard(self, clean_db):
        """Test viewing leaderboard."""
        from bot import menu_callback
        
        # Create some students with scores
        s1 = create_registered_student(111, "user1", "Top")
        s2 = create_registered_student(222, "user2", "Mid")
        
        user = MockUser(id=111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="menu:leaderboard", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await menu_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert "Лидерборд" in call_text
    
    @pytest.mark.asyncio
    async def test_menu_admin_non_admin(self, clean_db):
        """Test admin menu access by non-admin."""
        from bot import menu_callback
        
        create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="menu:admin", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await menu_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert call_text == "⛔"


class TestModulesCallback:
    """Tests for modules callback handler."""
    
    @pytest.mark.asyncio
    async def test_modules_list_empty(self, clean_db):
        """Test modules list when empty (besides default)."""
        from bot import modules_callback
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="modules:list", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await modules_callback(update, context)
        
        # Should show at least default module
        call_text = query.edit_message_text.call_args[0][0]
        assert "Модули" in call_text
    
    @pytest.mark.asyncio
    async def test_modules_list_with_data(self, clean_db):
        """Test modules list with modules."""
        from bot import modules_callback
        
        db.add_module("test_mod", "Test Module", 1, "python")
        create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="modules:list", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await modules_callback(update, context)
        
        # Check keyboard has module buttons
        call_kwargs = query.edit_message_text.call_args[1]
        keyboard = call_kwargs['reply_markup']
        buttons = [btn.text for row in keyboard.inline_keyboard for btn in row]
        any_module = any("🐍" in b or "🐹" in b for b in buttons)
        assert any_module


# ============= DECORATOR TESTS =============

class TestDecorators:
    """Tests for require_admin and require_registered decorators."""
    
    @pytest.mark.asyncio
    async def test_require_admin_non_admin(self, clean_db):
        """Test require_admin blocks non-admin."""
        from bot import require_admin
        
        @require_admin
        async def protected_func(update, context):
            return "success"
        
        user = MockUser(id=999999)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        result = await protected_func(update, context)
        
        assert result is None
        message.reply_text.assert_called()
        assert "админ" in message.reply_text.call_args[0][0].lower()
    
    @pytest.mark.asyncio
    async def test_require_admin_admin(self, clean_db):
        """Test require_admin allows admin."""
        from bot import require_admin
        
        create_admin(123456)
        
        @require_admin
        async def protected_func(update, context):
            return "success"
        
        user = MockUser(id=123456)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        result = await protected_func(update, context)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_require_registered_unregistered(self, clean_db):
        """Test require_registered blocks unregistered."""
        from bot import require_registered
        
        @require_registered
        async def protected_func(update, context):
            return "success"
        
        user = MockUser(id=999999)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        result = await protected_func(update, context)
        
        assert result is None
        message.reply_text.assert_called()
        assert "register" in message.reply_text.call_args[0][0].lower()
    
    @pytest.mark.asyncio
    async def test_require_registered_registered(self, clean_db):
        """Test require_registered allows registered."""
        from bot import require_registered
        
        create_registered_student(111111)
        
        @require_registered
        async def protected_func(update, context):
            return "success"
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        result = await protected_func(update, context)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_require_registered_admin(self, clean_db):
        """Test require_registered allows admin even if not registered as student."""
        from bot import require_registered
        
        create_admin(123456)
        
        @require_registered
        async def protected_func(update, context):
            return "success"
        
        user = MockUser(id=123456)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        result = await protected_func(update, context)
        assert result == "success"


# ============= CODE RUNNER TESTS =============

class TestCodeRunner:
    """Tests for code execution functions."""
    
    @pytest.mark.skipif(sys.platform == 'win32', reason="Emoji encoding issues on Windows")
    def test_run_python_success(self, clean_db):
        """Test running passing Python code."""
        from bot import run_python_code_with_tests
        
        code = "def add(a, b): return a + b"
        test_code = "result = add(2, 3)\nassert result == 5\nprint('✅')"
        
        passed, output = run_python_code_with_tests(code, test_code)
        assert passed is True
        assert "✅" in output
    
    def test_run_python_failure(self, clean_db):
        """Test running failing Python code."""
        from bot import run_python_code_with_tests
        
        code = "def add(a, b): return a - b"  # Wrong implementation
        test_code = "assert add(2, 3) == 5\nprint('OK')"
        
        passed, output = run_python_code_with_tests(code, test_code)
        assert passed is False
    
    def test_run_python_syntax_error(self, clean_db):
        """Test running code with syntax error."""
        from bot import run_python_code_with_tests
        
        code = "def broken("
        test_code = "print('test')"
        
        passed, output = run_python_code_with_tests(code, test_code)
        assert passed is False
        assert "Error" in output or "error" in output.lower() or "Syntax" in output
    
    @pytest.mark.skipif(sys.platform == 'win32', reason="Emoji encoding issues on Windows")
    def test_run_code_dispatcher_python(self, clean_db):
        """Test universal runner dispatches to Python."""
        from bot import run_code_with_tests
        
        code = "def multiply(x, y): return x * y"
        test_code = "assert multiply(4, 5) == 20\nprint('✅')"
        
        passed, output = run_code_with_tests(code, test_code, "python")
        assert passed is True


# ============= NOTIFICATION TESTS =============

class TestNotifications:
    """Tests for notification functions."""
    
    @pytest.mark.asyncio
    async def test_notify_student(self, clean_db):
        """Test notifying a student."""
        from bot import notify_student
        
        student = create_registered_student(111111)
        context = MockContext()
        
        result = await notify_student(context, 111111, "Test message")
        
        context.bot.send_message.assert_called_once()
        call_kwargs = context.bot.send_message.call_args[1]
        assert call_kwargs['chat_id'] == 111111
        assert call_kwargs['text'] == "Test message"
    
    @pytest.mark.asyncio
    async def test_notify_mentors(self, clean_db):
        """Test notifying mentors of a student."""
        from bot import notify_mentors
        
        create_admin(123456)
        student = create_registered_student(111111)
        db.assign_mentor(student['id'], 123456)
        
        context = MockContext()
        
        sent = await notify_mentors(context, student['id'], "Test message")
        
        assert sent == 1
        context.bot.send_message.assert_called()
    
    @pytest.mark.asyncio
    async def test_notify_mentors_fallback(self, clean_db):
        """Test notify_mentors falls back to all admins."""
        from bot import notify_mentors
        
        create_admin(111)
        create_admin(222)
        student = create_registered_student(333)
        # No mentor assigned
        
        context = MockContext()
        
        sent = await notify_mentors(context, student['id'], "Test", fallback_to_all=True)
        
        # Should have notified both admins
        assert sent == 2


# ============= DAILY SPIN CALLBACK TESTS =============

class TestDailySpinCallback:
    """Tests for daily spin callback."""
    
    @pytest.mark.asyncio
    async def test_dailyspin_available(self, clean_db):
        """Test daily spin when available."""
        from bot import dailyspin_callback
        
        student = create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="dailyspin", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await dailyspin_callback(update, context)
        
        query.answer.assert_called()
        # Should show result
        call_text = query.edit_message_text.call_args[0][0]
        # Result should contain points info
        assert any(x in call_text for x in ["🎰", "рулетка", "баллов", "+", "-"])


# ============= TEXT MESSAGE HANDLER TESTS =============

class TestTextHandler:
    """Tests for text message handler."""
    
    @pytest.mark.asyncio
    async def test_text_handler_no_context(self, clean_db):
        """Test text handler with no special context."""
        from bot import handle_text
        
        user = MockUser(id=111111)
        message = MockMessage(text="Hello bot", from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        # Should not raise, just return
        await handle_text(update, context)
    
    @pytest.mark.asyncio
    async def test_text_handler_creating_module(self, clean_db):
        """Test text handler when admin is creating module."""
        from bot import handle_text
        
        create_admin(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(text="newmod Test Module", from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext(user_data={"creating": "module"})
        
        await handle_text(update, context)
        
        # Should have created module
        module = db.get_module("newmod")
        assert module is not None
        assert module['name'] == "Test Module"


# ============= SHAMEBOARD TESTS =============

class TestShameboard:
    """Tests for shameboard (cheaters board)."""
    
    @pytest.mark.asyncio
    async def test_shameboard_empty(self, clean_db):
        """Test shameboard when no cheaters."""
        from bot import menu_callback
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="menu:shameboard", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await menu_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert "чисто" in call_text.lower() or "Пока" in call_text
    
    @pytest.mark.asyncio
    async def test_shameboard_with_cheaters(self, clean_db):
        """Test shameboard with cheaters."""
        from bot import menu_callback
        
        student = create_registered_student(111111, "cheater", "Cheater")
        create_task_with_topic("task1", "t1", "m1")
        sub_id = db.add_submission(student['id'], "task1", "code", True, "out")
        db.punish_cheater(sub_id, 0)
        
        user = MockUser(id=222222)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="menu:shameboard", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await menu_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert "ПОЗОРА" in call_text
        assert "Cheater" in call_text
