"""
Shared pytest fixtures for testing the Telegram bot.
Provides mocks for database, Telegram API, and common test utilities.
"""
import os
import sys
import pytest
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from typing import Optional, Dict, Any, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment
os.environ["BOT_TOKEN"] = "TEST_TOKEN_12345"

# Import after path setup
import database as db


# ============= DATABASE FIXTURES =============

@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_mentor.db"
    original_path = db.DB_PATH
    db.DB_PATH = db_path
    db.init_db()
    yield db_path
    db.DB_PATH = original_path


@pytest.fixture
def clean_db(temp_db):
    """Provide a clean initialized database."""
    return temp_db


@pytest.fixture
def populated_db(temp_db):
    """Database with sample data for testing."""
    # Create admin
    db.add_admin(123456789, "TestAdmin")
    
    # Create codes
    codes = db.create_codes(5)
    
    # Create students
    db.register_student(111111111, "student1", "Иван", codes[0])
    db.register_student(222222222, "student2", "Мария", codes[1])
    db.register_student(333333333, "student3", "Алексей", codes[2])
    
    # Create module
    db.add_module("py_basics", "Основы Python", 1, "python")
    db.add_module("go_basics", "Основы Go", 2, "go")
    
    # Create topics
    db.add_topic("variables", "Переменные", "py_basics", 1)
    db.add_topic("functions", "Функции", "py_basics", 2)
    db.add_topic("go_intro", "Введение в Go", "go_basics", 1)
    
    # Create tasks
    db.add_task(
        "var_1", "variables", "Создай переменную",
        "Создайте переменную x = 10",
        "assert x == 10\nprint('✅')",
        "python"
    )
    db.add_task(
        "func_1", "functions", "Напиши функцию",
        "Напишите функцию double(n)",
        "assert double(5) == 10\nprint('✅')",
        "python"
    )
    
    return temp_db


# ============= TELEGRAM MOCK FIXTURES =============

class MockUser:
    """Mock Telegram User object."""
    def __init__(
        self,
        id: int = 111111111,
        username: str = "testuser",
        first_name: str = "Test",
        last_name: str = "User",
        is_bot: bool = False
    ):
        self.id = id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.is_bot = is_bot


class MockChat:
    """Mock Telegram Chat object."""
    def __init__(
        self,
        id: int = 111111111,
        type: str = "private",
        title: str = None
    ):
        self.id = id
        self.type = type
        self.title = title


class MockMessage:
    """Mock Telegram Message object."""
    def __init__(
        self,
        text: str = "",
        chat: MockChat = None,
        from_user: MockUser = None,
        entities: list = None,
        message_id: int = 1
    ):
        self.text = text
        self.chat = chat or MockChat()
        self.from_user = from_user or MockUser()
        self.entities = entities or []
        self.message_id = message_id
        self.reply_text = AsyncMock()
        self.reply_html = AsyncMock()
        self.delete = AsyncMock()
        self.edit_text = AsyncMock()


class MockCallbackQuery:
    """Mock Telegram CallbackQuery object."""
    def __init__(
        self,
        data: str = "",
        from_user: MockUser = None,
        message: MockMessage = None,
        id: str = "callback_123"
    ):
        self.data = data
        self.from_user = from_user or MockUser()
        self.message = message or MockMessage()
        self.id = id
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()
        self.edit_message_reply_markup = AsyncMock()


class MockUpdate:
    """Mock Telegram Update object."""
    def __init__(
        self,
        message: MockMessage = None,
        callback_query: MockCallbackQuery = None,
        effective_user: MockUser = None,
        update_id: int = 1
    ):
        self.message = message
        self.callback_query = callback_query
        self.effective_user = effective_user or (message.from_user if message else MockUser())
        self.update_id = update_id
        self.effective_chat = message.chat if message else MockChat()


class MockContext:
    """Mock Telegram Context object."""
    def __init__(self, args: list = None, user_data: dict = None):
        self.args = args or []
        self.user_data = user_data or {}
        self.bot_data = {}
        self.chat_data = {}
        self.bot = MockBot()
        self.job_queue = MagicMock()


class MockBot:
    """Mock Telegram Bot object."""
    def __init__(self):
        self.send_message = AsyncMock()
        self.edit_message_text = AsyncMock()
        self.delete_message = AsyncMock()
        self.get_me = AsyncMock(return_value=MockUser(id=999999, username="test_bot", is_bot=True))


@pytest.fixture
def mock_user():
    """Create a mock Telegram user."""
    return MockUser()


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user."""
    return MockUser(id=123456789, username="qwerty1492", first_name="Admin")


@pytest.fixture
def mock_message(mock_user):
    """Create a mock message."""
    return MockMessage(from_user=mock_user)


@pytest.fixture
def mock_update(mock_message):
    """Create a mock update with message."""
    return MockUpdate(message=mock_message)


@pytest.fixture
def mock_callback_update():
    """Create a mock update with callback query."""
    user = MockUser()
    message = MockMessage(from_user=user)
    callback = MockCallbackQuery(from_user=user, message=message)
    return MockUpdate(callback_query=callback, effective_user=user)


@pytest.fixture
def mock_context():
    """Create a mock context."""
    return MockContext()


# ============= FACTORY FIXTURES =============

@pytest.fixture
def update_factory():
    """Factory for creating mock updates."""
    def _create_update(
        text: str = "",
        user_id: int = 111111111,
        username: str = "testuser",
        first_name: str = "Test",
        args: list = None,
        callback_data: str = None
    ) -> tuple[MockUpdate, MockContext]:
        user = MockUser(id=user_id, username=username, first_name=first_name)
        
        if callback_data:
            message = MockMessage(from_user=user)
            callback = MockCallbackQuery(data=callback_data, from_user=user, message=message)
            update = MockUpdate(callback_query=callback, effective_user=user)
        else:
            message = MockMessage(text=text, from_user=user)
            update = MockUpdate(message=message, effective_user=user)
        
        context = MockContext(args=args or [])
        return update, context
    
    return _create_update


@pytest.fixture
def student_factory(clean_db):
    """Factory for creating test students."""
    def _create_student(
        user_id: int = None,
        username: str = None,
        first_name: str = None
    ) -> Dict:
        import random
        user_id = user_id or random.randint(100000000, 999999999)
        username = username or f"user_{user_id}"
        first_name = first_name or f"Name_{user_id}"
        
        codes = db.create_codes(1)
        db.register_student(user_id, username, first_name, codes[0])
        return db.get_student(user_id)
    
    return _create_student


@pytest.fixture
def task_factory(clean_db):
    """Factory for creating test tasks."""
    def _create_task(
        task_id: str = None,
        topic_id: str = "test_topic",
        title: str = "Test Task",
        description: str = "Test description",
        test_code: str = "print('✅')",
        language: str = "python"
    ) -> Dict:
        import random
        task_id = task_id or f"task_{random.randint(1000, 9999)}"
        
        # Ensure topic exists
        if not db.get_topic(topic_id):
            # Ensure module exists
            if not db.get_module("test_module"):
                db.add_module("test_module", "Test Module", 1, language)
            db.add_topic(topic_id, "Test Topic", "test_module", 1)
        
        db.add_task(task_id, topic_id, title, description, test_code, language)
        return db.get_task(task_id)
    
    return _create_task


# ============= UTILITY FIXTURES =============

@pytest.fixture
def freeze_time():
    """Fixture to freeze time for tests."""
    from unittest.mock import patch
    
    def _freeze(dt: datetime = None):
        if dt is None:
            dt = datetime(2025, 6, 15, 12, 0, 0)
        
        class FrozenDatetime:
            @classmethod
            def now(cls, tz=None):
                if tz:
                    return dt.replace(tzinfo=tz)
                return dt
            
            @classmethod
            def fromisoformat(cls, s):
                return datetime.fromisoformat(s)
        
        return patch('database.datetime', FrozenDatetime)
    
    return _freeze


@pytest.fixture
def capture_notifications():
    """Capture bot notifications for verification."""
    notifications = []
    
    async def capture(chat_id, text, **kwargs):
        notifications.append({
            "chat_id": chat_id,
            "text": text,
            **kwargs
        })
    
    return notifications, capture


# ============= HELPER FUNCTIONS =============

def create_registered_student(user_id: int, username: str = "testuser", first_name: str = "Test"):
    """Helper to create and register a student."""
    codes = db.create_codes(1)
    db.register_student(user_id, username, first_name, codes[0])
    return db.get_student(user_id)


def create_admin(user_id: int, name: str = "Admin"):
    """Helper to create an admin."""
    db.add_admin(user_id, name)
    return user_id


def create_task_with_topic(
    task_id: str,
    topic_id: str,
    module_id: str = "test_module",
    title: str = "Test",
    description: str = "Test desc",
    test_code: str = "print('✅')",
    language: str = "python"
):
    """Helper to create task with its dependencies."""
    if not db.get_module(module_id):
        db.add_module(module_id, "Test Module", 1, language)
    if not db.get_topic(topic_id):
        db.add_topic(topic_id, "Test Topic", module_id, 1)
    db.add_task(task_id, topic_id, title, description, test_code, language)
    return db.get_task(task_id)
