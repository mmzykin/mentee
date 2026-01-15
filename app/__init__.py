"""
Mentee Bot Application Package

Structure:
- config.py      - Configuration constants
- utils.py       - Utility functions
- keyboards.py   - Inline keyboard builders
- decorators.py  - Handler decorators (@require_admin, @require_registered)
- code_runner.py - Code execution (Python/Go sandboxed)
- notifications.py - Notification helpers
- background.py  - Background tasks (meeting reminders)
- main.py        - Application entry point and handler registration
- handlers/      - All bot handlers organized by domain
"""
from app.main import main

__all__ = ["main"]
