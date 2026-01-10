"""
Database models and manager for Mentor Bot
SQLite with students, tasks, topics, submissions, and registration codes
"""

import sqlite3
import secrets
import string
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

DB_PATH = Path("data/mentor.db")


def generate_code(length: int = 8) -> str:
    """Generate a unique registration code."""
    alphabet = string.ascii_uppercase + string.digits
    # Remove confusing characters
    alphabet = alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


@contextmanager
def get_db():
    """Context manager for database connections."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Initialize database tables."""
    with get_db() as conn:
        conn.executescript("""
            -- Registration codes
            CREATE TABLE IF NOT EXISTS codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                used_by INTEGER,
                created_at TEXT NOT NULL,
                used_at TEXT
            );
            
            -- Students (registered users)
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                code_used TEXT NOT NULL,
                registered_at TEXT NOT NULL
            );
            
            -- Topics
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                order_num INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            
            -- Tasks
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT UNIQUE NOT NULL,
                topic_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                test_code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (topic_id) REFERENCES topics(topic_id)
            );
            
            -- Submissions
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                task_id TEXT NOT NULL,
                code TEXT NOT NULL,
                passed INTEGER NOT NULL,
                output TEXT,
                submitted_at TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(id),
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            );
            
            -- Admins
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                added_at TEXT NOT NULL
            );
            
            -- Create indexes
            CREATE INDEX IF NOT EXISTS idx_submissions_student ON submissions(student_id);
            CREATE INDEX IF NOT EXISTS idx_submissions_task ON submissions(task_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_topic ON tasks(topic_id);
        """)


# ============== ADMIN FUNCTIONS ==============

def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    with get_db() as conn:
        result = conn.execute(
            "SELECT 1 FROM admins WHERE user_id = ?", (user_id,)
        ).fetchone()
        return result is not None


def add_admin(user_id: int) -> bool:
    """Add a new admin."""
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO admins (user_id, added_at) VALUES (?, ?)",
                (user_id, datetime.now().isoformat())
            )
            return True
        except sqlite3.IntegrityError:
            return False


def get_admin_count() -> int:
    """Get number of admins."""
    with get_db() as conn:
        result = conn.execute("SELECT COUNT(*) FROM admins").fetchone()
        return result[0]


# ============== CODE FUNCTIONS ==============

def create_codes(count: int) -> List[str]:
    """Generate multiple registration codes."""
    codes = []
    with get_db() as conn:
        for _ in range(count):
            while True:
                code = generate_code()
                try:
                    conn.execute(
                        "INSERT INTO codes (code, created_at) VALUES (?, ?)",
                        (code, datetime.now().isoformat())
                    )
                    codes.append(code)
                    break
                except sqlite3.IntegrityError:
                    continue  # Code exists, try again
    return codes


def get_unused_codes() -> List[Dict]:
    """Get all unused registration codes."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT code, created_at FROM codes WHERE used_by IS NULL ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def use_code(code: str, user_id: int) -> bool:
    """Mark code as used. Returns True if successful."""
    with get_db() as conn:
        result = conn.execute(
            "SELECT id, used_by FROM codes WHERE code = ?", (code.upper(),)
        ).fetchone()
        
        if not result:
            return False  # Code doesn't exist
        
        if result["used_by"] is not None:
            return False  # Already used
        
        conn.execute(
            "UPDATE codes SET used_by = ?, used_at = ? WHERE code = ?",
            (user_id, datetime.now().isoformat(), code.upper())
        )
        return True


def delete_code(code: str) -> bool:
    """Delete an unused code."""
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM codes WHERE code = ? AND used_by IS NULL", (code.upper(),)
        )
        return result.rowcount > 0


# ============== STUDENT FUNCTIONS ==============

def register_student(user_id: int, username: str, first_name: str, code: str) -> bool:
    """Register a new student with a code."""
    # First check and use the code
    if not use_code(code, user_id):
        return False
    
    with get_db() as conn:
        try:
            conn.execute(
                """INSERT INTO students (user_id, username, first_name, code_used, registered_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, username, first_name, code.upper(), datetime.now().isoformat())
            )
            return True
        except sqlite3.IntegrityError:
            return False  # Already registered


def get_student(user_id: int) -> Optional[Dict]:
    """Get student by user_id."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_students() -> List[Dict]:
    """Get all registered students."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM students ORDER BY registered_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def is_registered(user_id: int) -> bool:
    """Check if user is registered."""
    return get_student(user_id) is not None


# ============== TOPIC FUNCTIONS ==============

def add_topic(topic_id: str, name: str, order_num: int = 0) -> bool:
    """Add a new topic."""
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO topics (topic_id, name, order_num, created_at) VALUES (?, ?, ?, ?)",
                (topic_id, name, order_num, datetime.now().isoformat())
            )
            return True
        except sqlite3.IntegrityError:
            return False


def get_topics() -> List[Dict]:
    """Get all topics ordered by order_num."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM topics ORDER BY order_num, topic_id"
        ).fetchall()
        return [dict(r) for r in rows]


def get_topic(topic_id: str) -> Optional[Dict]:
    """Get topic by topic_id."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM topics WHERE topic_id = ?", (topic_id,)
        ).fetchone()
        return dict(row) if row else None


def delete_topic(topic_id: str) -> bool:
    """Delete a topic (only if no tasks)."""
    with get_db() as conn:
        # Check for tasks
        tasks = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE topic_id = ?", (topic_id,)
        ).fetchone()[0]
        
        if tasks > 0:
            return False
        
        result = conn.execute(
            "DELETE FROM topics WHERE topic_id = ?", (topic_id,)
        )
        return result.rowcount > 0


# ============== TASK FUNCTIONS ==============

def add_task(task_id: str, topic_id: str, title: str, description: str, test_code: str) -> bool:
    """Add a new task."""
    with get_db() as conn:
        try:
            conn.execute(
                """INSERT INTO tasks (task_id, topic_id, title, description, test_code, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task_id, topic_id, title, description, test_code, datetime.now().isoformat())
            )
            return True
        except sqlite3.IntegrityError:
            return False


def get_task(task_id: str) -> Optional[Dict]:
    """Get task by task_id."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return dict(row) if row else None


def get_tasks_by_topic(topic_id: str) -> List[Dict]:
    """Get all tasks for a topic."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE topic_id = ? ORDER BY task_id", (topic_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_tasks() -> List[Dict]:
    """Get all tasks."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY topic_id, task_id"
        ).fetchall()
        return [dict(r) for r in rows]


def update_task(task_id: str, title: str = None, description: str = None, test_code: str = None) -> bool:
    """Update task fields."""
    with get_db() as conn:
        task = get_task(task_id)
        if not task:
            return False
        
        conn.execute(
            """UPDATE tasks SET title = ?, description = ?, test_code = ? WHERE task_id = ?""",
            (
                title if title else task["title"],
                description if description else task["description"],
                test_code if test_code else task["test_code"],
                task_id
            )
        )
        return True


def delete_task(task_id: str) -> bool:
    """Delete a task."""
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM tasks WHERE task_id = ?", (task_id,)
        )
        return result.rowcount > 0


# ============== SUBMISSION FUNCTIONS ==============

def add_submission(student_id: int, task_id: str, code: str, passed: bool, output: str) -> int:
    """Add a submission. Returns submission id."""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO submissions (student_id, task_id, code, passed, output, submitted_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (student_id, task_id, code, int(passed), output[:5000], datetime.now().isoformat())
        )
        return cursor.lastrowid


def get_student_submissions(student_id: int, task_id: str = None) -> List[Dict]:
    """Get submissions for a student, optionally filtered by task."""
    with get_db() as conn:
        if task_id:
            rows = conn.execute(
                """SELECT * FROM submissions WHERE student_id = ? AND task_id = ?
                   ORDER BY submitted_at DESC""",
                (student_id, task_id)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM submissions WHERE student_id = ? ORDER BY submitted_at DESC",
                (student_id,)
            ).fetchall()
        return [dict(r) for r in rows]


def has_solved(student_id: int, task_id: str) -> bool:
    """Check if student has solved a task."""
    with get_db() as conn:
        result = conn.execute(
            "SELECT 1 FROM submissions WHERE student_id = ? AND task_id = ? AND passed = 1",
            (student_id, task_id)
        ).fetchone()
        return result is not None


def get_student_stats(student_id: int) -> Dict:
    """Get statistics for a student."""
    with get_db() as conn:
        # Total submissions
        total = conn.execute(
            "SELECT COUNT(*) FROM submissions WHERE student_id = ?", (student_id,)
        ).fetchone()[0]
        
        # Solved tasks
        solved = conn.execute(
            """SELECT COUNT(DISTINCT task_id) FROM submissions 
               WHERE student_id = ? AND passed = 1""", (student_id,)
        ).fetchone()[0]
        
        # Total tasks
        total_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        
        return {
            "total_submissions": total,
            "solved_tasks": solved,
            "total_tasks": total_tasks
        }


def get_all_students_stats() -> List[Dict]:
    """Get stats for all students."""
    students = get_all_students()
    result = []
    
    for student in students:
        stats = get_student_stats(student["id"])
        result.append({
            **student,
            **stats
        })
    
    return result


def get_student_by_id(student_id: int) -> Optional[Dict]:
    """Get student by internal ID (not user_id)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        return dict(row) if row else None


def get_submission_by_id(submission_id: int) -> Optional[Dict]:
    """Get submission by ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM submissions WHERE id = ?", (submission_id,)
        ).fetchone()
        return dict(row) if row else None


# Initialize on import
init_db()
