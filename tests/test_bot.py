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


# ============= TOPIC CALLBACK TESTS =============

class TestTopicCallback:
    """Tests for topic navigation callback."""
    
    @pytest.mark.asyncio
    async def test_topic_callback_valid(self, clean_db):
        """Test viewing a valid topic with tasks."""
        from bot import topic_callback
        
        create_task_with_topic("task1", "test_topic", "test_module")
        student = create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="topic:test_topic", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await topic_callback(update, context)
        
        query.answer.assert_called()
        call_text = query.edit_message_text.call_args[0][0]
        # Should show topic name
        assert "Test Topic" in call_text
    
    @pytest.mark.asyncio
    async def test_topic_callback_invalid(self, clean_db):
        """Test viewing invalid topic."""
        from bot import topic_callback
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="topic:nonexistent", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await topic_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert "Не найден" in call_text
    
    @pytest.mark.asyncio
    async def test_topic_shows_solved_status(self, clean_db):
        """Test topic shows solved checkmark for completed tasks."""
        from bot import topic_callback
        
        task = create_task_with_topic("task1", "test_topic", "test_module")
        student = create_registered_student(111111)
        # Mark task as solved
        db.add_submission(student['id'], "task1", "code", True, "✅")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="topic:test_topic", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await topic_callback(update, context)
        
        # Check keyboard has checkmark for solved task
        call_kwargs = query.edit_message_text.call_args[1]
        keyboard = call_kwargs['reply_markup']
        buttons = [btn.text for row in keyboard.inline_keyboard for btn in row]
        any_solved = any("✅" in b for b in buttons)
        assert any_solved


# ============= TASK CALLBACK TESTS =============

class TestTaskCallback:
    """Tests for task viewing callback."""
    
    @pytest.mark.asyncio
    async def test_task_callback_shows_choice(self, clean_db):
        """Test task callback shows mode choice first."""
        from bot import task_callback
        
        create_task_with_topic("task1", "test_topic", "test_module", title="Test Task")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="task:task1", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await task_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        # Should show mode choice
        assert "режим" in call_text.lower() or "Test Task" in call_text
    
    @pytest.mark.asyncio
    async def test_task_callback_invalid(self, clean_db):
        """Test task callback with invalid task."""
        from bot import task_callback
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="task:nonexistent", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await task_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert "Не найден" in call_text


# ============= OPENTASK CALLBACK TESTS =============

class TestOpentaskCallback:
    """Tests for opening task without timer."""
    
    @pytest.mark.asyncio
    async def test_opentask_sets_no_timer_mode(self, clean_db):
        """Test opentask sets no_timer flag."""
        from bot import opentask_callback
        
        create_task_with_topic("task1", "test_topic", "test_module", description="Task description here")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="opentask:task1", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await opentask_callback(update, context)
        
        # Check no_timer_task was set
        assert context.user_data.get("no_timer_task") == "task1"
        # Should show task content
        call_text = query.edit_message_text.call_args[0][0]
        assert "Task description" in call_text or "task1" in call_text


# ============= TIMER CALLBACK TESTS =============

class TestTimerCallbacks:
    """Tests for timer-related callbacks."""
    
    @pytest.mark.asyncio
    async def test_starttimer_no_bet(self, clean_db):
        """Test starting timer without bet."""
        from bot import starttimer_callback
        
        create_task_with_topic("task1", "test_topic", "test_module")
        student = create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="starttimer:task1:0", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await starttimer_callback(update, context)
        
        # Timer should be set
        assert context.user_data.get("task_timer") is not None
        assert context.user_data["task_timer"]["task_id"] == "task1"
        assert context.user_data["task_timer"]["bet"] == 0
    
    @pytest.mark.asyncio
    async def test_starttimer_with_bet_enough_points(self, clean_db):
        """Test starting timer with bet when student has enough points."""
        from bot import starttimer_callback
        
        create_task_with_topic("task1", "test_topic", "test_module")
        student = create_registered_student(111111)
        db.add_bonus_points(student['id'], 10)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="starttimer:task1:2", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await starttimer_callback(update, context)
        
        # Timer should be set with bet
        assert context.user_data["task_timer"]["bet"] == 2
        # Points should be deducted
        updated_student = db.get_student(111111)
        assert updated_student['bonus_points'] == 8
    
    @pytest.mark.asyncio
    async def test_starttimer_with_bet_not_enough_points(self, clean_db):
        """Test starting timer with bet when student doesn't have enough points."""
        from bot import starttimer_callback
        
        create_task_with_topic("task1", "test_topic", "test_module")
        student = create_registered_student(111111)
        # No points added
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="starttimer:task1:5", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await starttimer_callback(update, context)
        
        # Should show error, timer not set
        query.answer.assert_called()
        call_args = query.answer.call_args
        assert "Недостаточно" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_resettimer_refunds_bet(self, clean_db):
        """Test resetting timer refunds bet."""
        from bot import resettimer_callback
        
        create_task_with_topic("task1", "test_topic", "test_module")
        student = create_registered_student(111111)
        db.add_bonus_points(student['id'], 10)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="resettimer:task1", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        
        # Simulate timer with bet
        from datetime import datetime
        context = MockContext(user_data={
            "task_timer": {
                "task_id": "task1",
                "start_time": datetime.now(),
                "bet": 3
            }
        })
        
        await resettimer_callback(update, context)
        
        # Timer should be cleared
        assert context.user_data.get("task_timer") is None
        # Bet should be refunded
        updated_student = db.get_student(111111)
        assert updated_student['bonus_points'] == 13  # 10 + 3 refund


# ============= GAMBLE CALLBACK TESTS =============

class TestGambleCallback:
    """Tests for gambling callback."""
    
    @pytest.mark.asyncio
    async def test_gamble_callback_bet(self, clean_db):
        """Test gamble bet."""
        from bot import gamble_callback
        
        student = create_registered_student(111111)
        db.add_bonus_points(student['id'], 10)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        # gamble:AMOUNT format
        query = MockCallbackQuery(data="gamble:2", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await gamble_callback(update, context)
        
        # Result should show win or lose
        call_text = query.edit_message_text.call_args[0][0]
        assert "УДВОИЛ" in call_text or "Проиграл" in call_text
    
    @pytest.mark.asyncio
    async def test_gamble_not_registered(self, clean_db):
        """Test gamble callback for unregistered user."""
        from bot import gamble_callback
        
        user = MockUser(id=999999)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="gamble:1", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await gamble_callback(update, context)
        
        # Should show error (no edit, just answer)
        query.answer.assert_called()
    
    @pytest.mark.asyncio
    async def test_gamble_not_enough_points(self, clean_db):
        """Test gamble with insufficient points."""
        from bot import gamble_callback
        
        student = create_registered_student(111111)
        # No bonus points
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="gamble:5", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await gamble_callback(update, context)
        
        # Should show insufficient points error
        call_args = query.answer.call_args
        assert "Недостаточно" in call_args[0][0]


# ============= ADMIN CALLBACK TESTS =============

class TestAdminCallback:
    """Tests for admin panel callbacks."""
    
    @pytest.mark.asyncio
    async def test_admin_modules_list(self, clean_db):
        """Test admin modules list."""
        from bot import admin_callback
        
        create_admin(111111)
        db.add_module("test_mod", "Test Module", 1, "python")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="admin:modules", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await admin_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert "Модул" in call_text
    
    @pytest.mark.asyncio
    async def test_admin_topics_list(self, clean_db):
        """Test admin topics list."""
        from bot import admin_callback
        
        create_admin(111111)
        db.add_module("mod1", "Module 1", 1, "python")
        db.add_topic("topic1", "Topic 1", "mod1", 1)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="admin:topics", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await admin_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert "Тем" in call_text
    
    @pytest.mark.asyncio
    async def test_admin_students_list(self, clean_db):
        """Test admin students list."""
        from bot import admin_callback
        
        create_admin(111111)
        create_registered_student(222222, "student1", "Student One")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="admin:students", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await admin_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        # Should show student count or list (text is "Активные студенты")
        assert "студент" in call_text.lower() or "ученик" in call_text.lower()
    
    @pytest.mark.asyncio
    async def test_admin_codes_list(self, clean_db):
        """Test admin codes list."""
        from bot import admin_callback
        
        create_admin(111111)
        codes = db.create_codes(3)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="admin:codes", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await admin_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert "Код" in call_text or "код" in call_text
    
    @pytest.mark.asyncio
    async def test_admin_non_admin_blocked(self, clean_db):
        """Test admin callback blocks non-admin."""
        from bot import admin_callback
        
        create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="admin:modules", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await admin_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert "⛔" in call_text
    
    @pytest.mark.asyncio
    async def test_admin_my_students(self, clean_db):
        """Test admin viewing their assigned students."""
        from bot import admin_callback
        
        create_admin(111111)
        student = create_registered_student(222222, "student1", "My Student")
        db.assign_mentor(student['id'], 111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="admin:mystudents", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await admin_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        # Should show mentor's students
        assert "ученик" in call_text.lower() or "My Student" in call_text


# ============= STUDENT CALLBACK TESTS =============

class TestStudentCallback:
    """Tests for student profile callback."""
    
    @pytest.mark.asyncio
    async def test_student_profile_view(self, clean_db):
        """Test viewing student profile."""
        from bot import student_callback
        
        create_admin(111111)
        student = create_registered_student(222222, "teststudent", "Test Student")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        # callback format is "student:USER_ID" (telegram user_id, not internal id)
        query = MockCallbackQuery(data="student:222222", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await student_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        # Should show student info
        assert "Test Student" in call_text or "teststudent" in call_text
    
    @pytest.mark.asyncio
    async def test_student_not_found(self, clean_db):
        """Test viewing non-existent student."""
        from bot import student_callback
        
        create_admin(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="student:99999999", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await student_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert "Не найден" in call_text or "не найден" in call_text.lower()


# ============= MY ATTEMPTS CALLBACK TESTS =============

class TestMyAttemptsCallback:
    """Tests for my attempts callback."""
    
    @pytest.mark.asyncio
    async def test_myattempts_with_submissions(self, clean_db):
        """Test viewing own attempts with submissions."""
        from bot import myattempts_callback
        
        student = create_registered_student(111111, "student", "Student")
        create_task_with_topic("task1", "t1", "m1")
        db.add_submission(student['id'], "task1", "code1", True, "✅")
        db.add_submission(student['id'], "task1", "code2", False, "Error")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="myattempts:0", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await myattempts_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        # Should show attempts
        assert "попытк" in call_text.lower() or "task1" in call_text
    
    @pytest.mark.asyncio
    async def test_myattempts_empty(self, clean_db):
        """Test viewing attempts when none exist."""
        from bot import myattempts_callback
        
        create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="myattempts:0", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await myattempts_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        # Should indicate no attempts
        assert "пуст" in call_text.lower() or "Нет" in call_text or "попыток" in call_text


# ============= MY ASSIGNED CALLBACK TESTS =============

class TestMyAssignedCallback:
    """Tests for my assigned tasks callback."""
    
    @pytest.mark.asyncio
    async def test_myassigned_with_tasks(self, clean_db):
        """Test viewing assigned tasks."""
        from bot import myassigned_callback
        
        student = create_registered_student(111111)
        create_task_with_topic("task1", "t1", "m1", title="Assigned Task")
        db.assign_task(student['id'], "task1")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="myassigned:0", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await myassigned_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        # Should show assigned tasks
        assert "Assigned Task" in call_text or "task1" in call_text or "Назначен" in call_text
    
    @pytest.mark.asyncio
    async def test_myassigned_empty(self, clean_db):
        """Test viewing assigned when none."""
        from bot import myassigned_callback
        
        create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="myassigned:0", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await myassigned_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        # Text is "Пока ничего не назначено"
        assert "ничего" in call_text.lower() or "Нет" in call_text or "пуст" in call_text.lower()


# ============= ANNOUNCEMENTS CALLBACK TESTS =============

class TestAnnouncementsCallback:
    """Tests for announcements callback."""
    
    @pytest.mark.asyncio
    async def test_announcements_list(self, clean_db):
        """Test viewing announcements list."""
        from bot import announcements_callback
        
        create_admin(111111)
        db.create_announcement("Test Announcement", "Content here", 111111)
        student = create_registered_student(222222)
        
        user = MockUser(id=222222)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="announcements:list", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await announcements_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert "Объявлен" in call_text or "Test Announcement" in call_text
    
    @pytest.mark.asyncio
    async def test_announcements_list_marks_read(self, clean_db):
        """Test viewing announcements list marks them as read."""
        from bot import announcements_callback
        
        create_admin(111111)
        db.create_announcement("Important News", "Full content", 111111)
        student = create_registered_student(222222)
        
        # Initially unread
        assert db.get_unread_announcements_count(student['id']) == 1
        
        user = MockUser(id=222222)
        message = MockMessage(from_user=user)
        # announcements:list marks all announcements as read
        query = MockCallbackQuery(data="announcements:list", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await announcements_callback(update, context)
        
        # Should be marked as read now
        assert db.get_unread_announcements_count(student['id']) == 0


# ============= QUIZ CALLBACK TESTS =============

class TestQuizCallback:
    """Tests for quiz callback."""
    
    @pytest.mark.asyncio
    async def test_quiz_menu(self, clean_db):
        """Test quiz menu display."""
        from bot import quiz_callback
        
        student = create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data="quiz:menu", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await quiz_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        # Should show quiz options
        assert "вопрос" in call_text.lower() or "квиз" in call_text.lower() or "Собес" in call_text


# ============= APPROVE/UNAPPROVE CALLBACK TESTS =============

class TestApprovalCallbacks:
    """Tests for approval callbacks."""
    
    @pytest.mark.asyncio
    async def test_approve_submission(self, clean_db):
        """Test approving a submission."""
        from bot import approve_callback
        
        create_admin(111111)
        student = create_registered_student(222222)
        create_task_with_topic("task1", "t1", "m1")
        sub_id = db.add_submission(student['id'], "task1", "code", True, "✅")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data=f"approve:{sub_id}", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await approve_callback(update, context)
        
        # Check submission was approved
        submission = db.get_submission_by_id(sub_id)
        assert submission['approved'] == 1
    
    @pytest.mark.asyncio
    async def test_unapprove_submission(self, clean_db):
        """Test unapproving a submission."""
        from bot import unapprove_callback
        
        create_admin(111111)
        student = create_registered_student(222222)
        create_task_with_topic("task1", "t1", "m1")
        sub_id = db.add_submission(student['id'], "task1", "code", True, "✅")
        db.approve_submission(sub_id, 1)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data=f"unapprove:{sub_id}", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await unapprove_callback(update, context)
        
        # Check submission was unapproved
        submission = db.get_submission_by_id(sub_id)
        assert submission['approved'] == 0


# ============= ASSIGN TASK CALLBACK TESTS =============

class TestAssignCallbacks:
    """Tests for task assignment callbacks."""
    
    @pytest.mark.asyncio
    async def test_assign_callback_menu(self, clean_db):
        """Test assign menu for student."""
        from bot import assign_callback
        
        create_admin(111111)
        student = create_registered_student(222222)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data=f"assign:{student['id']}", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await assign_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        # Should show assignment options
        assert "Назнач" in call_text or "модул" in call_text.lower()
    
    @pytest.mark.asyncio
    async def test_toggleassign_callback(self, clean_db):
        """Test toggling task assignment."""
        from bot import toggleassign_callback
        
        create_admin(111111)
        student = create_registered_student(222222)
        create_task_with_topic("task1", "t1", "m1")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        # toggleassign format is "toggleassign:TASK_ID" and uses context.user_data["assigning_to"]
        query = MockCallbackQuery(
            data="toggleassign:task1", 
            from_user=user, 
            message=message
        )
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext(user_data={"assigning_to": student['id']})
        
        await toggleassign_callback(update, context)
        
        # Task should now be assigned
        assert db.is_task_assigned(student['id'], "task1")


# ============= MENTOR CALLBACK TESTS =============

class TestMentorCallbacks:
    """Tests for mentor assignment callbacks."""
    
    @pytest.mark.asyncio
    async def test_mentors_view(self, clean_db):
        """Test viewing student's mentors."""
        from bot import mentors_callback
        
        create_admin(111111)
        student = create_registered_student(222222)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data=f"mentors:{student['id']}", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await mentors_callback(update, context)
        
        call_text = query.edit_message_text.call_args[0][0]
        assert "Ментор" in call_text or "ментор" in call_text
    
    @pytest.mark.asyncio
    async def test_addmentor_callback(self, clean_db):
        """Test adding mentor to student."""
        from bot import addmentor_callback
        
        create_admin(111111)
        create_admin(333333)  # Second admin to be mentor
        student = create_registered_student(222222)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(
            data=f"addmentor:{student['id']}:{333333}", 
            from_user=user, 
            message=message
        )
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await addmentor_callback(update, context)
        
        # Mentor should be assigned
        assert db.is_mentor_of(333333, student['id'])


# ============= CHEATER CALLBACK TESTS =============

class TestCheaterCallback:
    """Tests for cheater handling callbacks."""
    
    @pytest.mark.asyncio
    async def test_cheater_callback_mark(self, clean_db):
        """Test marking submission as cheated."""
        from bot import cheater_callback
        
        create_admin(111111)
        student = create_registered_student(222222)
        db.add_bonus_points(student['id'], 10)
        create_task_with_topic("task1", "t1", "m1")
        sub_id = db.add_submission(student['id'], "task1", "code", True, "✅")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data=f"cheater:{sub_id}:3", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await cheater_callback(update, context)
        
        # Check submission marked and penalty applied
        submission = db.get_submission_by_id(sub_id)
        assert submission['passed'] == 0
        assert "СПИСАНО" in submission['feedback']
        updated_student = db.get_student(222222)
        assert updated_student['bonus_points'] == 7  # 10 - 3 penalty


# ============= DELETE SUBMISSION CALLBACK TESTS =============

class TestDelsubCallback:
    """Tests for delete submission callback."""
    
    @pytest.mark.asyncio
    async def test_delsub_callback(self, clean_db):
        """Test deleting a submission."""
        from bot import delsub_callback
        
        create_admin(111111)
        student = create_registered_student(222222)
        create_task_with_topic("task1", "t1", "m1")
        sub_id = db.add_submission(student['id'], "task1", "code", True, "✅")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        query = MockCallbackQuery(data=f"delsub:{sub_id}", from_user=user, message=message)
        update = MockUpdate(callback_query=query, effective_user=user)
        context = MockContext()
        
        await delsub_callback(update, context)
        
        # Submission should be deleted
        assert db.get_submission_by_id(sub_id) is None


# ============= COMMAND TESTS =============

class TestCommands:
    """Tests for command handlers."""
    
    @pytest.mark.asyncio
    async def test_topics_cmd(self, clean_db):
        """Test /topics command (requires registration)."""
        from bot import topics_cmd
        
        db.add_module("mod1", "Test Module", 1, "python")
        db.add_topic("topic1", "Test Topic", "mod1", 1)
        # Register user first (topics_cmd has @require_registered decorator)
        create_registered_student(111111)
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        await topics_cmd(update, context)
        
        message.reply_text.assert_called_once()
        call_text = message.reply_text.call_args[0][0]
        assert "Модул" in call_text or "📚" in call_text
    
    @pytest.mark.asyncio
    async def test_leaderboard_cmd(self, clean_db):
        """Test /leaderboard command."""
        from bot import leaderboard_cmd
        
        create_registered_student(111111, "top", "TopPlayer")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext()
        
        await leaderboard_cmd(update, context)
        
        message.reply_text.assert_called_once()
        call_text = message.reply_text.call_args[0][0]
        assert "Лидерборд" in call_text or "🏆" in call_text
    
    @pytest.mark.asyncio
    async def test_deltask_cmd_admin(self, clean_db):
        """Test /deltask command for admin."""
        from bot import del_task_cmd
        
        create_admin(111111)
        create_task_with_topic("task_to_delete", "t1", "m1")
        
        user = MockUser(id=111111)
        message = MockMessage(from_user=user)
        update = MockUpdate(message=message, effective_user=user)
        context = MockContext(args=["task_to_delete"])
        
        await del_task_cmd(update, context)
        
        # Task should be deleted
        assert db.get_task("task_to_delete") is None
