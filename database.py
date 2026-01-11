import sqlite3
import secrets
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from contextlib import contextmanager

DB_PATH = Path("data/mentor.db")
CODE_RETENTION_DAYS = 7


def generate_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    alphabet = alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


@contextmanager
def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                used_by INTEGER,
                created_at TEXT NOT NULL,
                used_at TEXT
            );
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                code_used TEXT NOT NULL,
                registered_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                order_num INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                order_num INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
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
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                task_id TEXT NOT NULL,
                code TEXT,
                passed INTEGER NOT NULL,
                output TEXT,
                submitted_at TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(id),
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            );
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                added_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assigned_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                task_id TEXT NOT NULL,
                assigned_at TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(id),
                FOREIGN KEY (task_id) REFERENCES tasks(task_id),
                UNIQUE(student_id, task_id)
            );
        """)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(topics)").fetchall()}
        if "module_id" not in cols:
            conn.execute("ALTER TABLE topics ADD COLUMN module_id TEXT DEFAULT '1'")
        cols = {row[1] for row in conn.execute("PRAGMA table_info(students)").fetchall()}
        if "bonus_points" not in cols:
            conn.execute("ALTER TABLE students ADD COLUMN bonus_points INTEGER DEFAULT 0")
        if "archived_at" not in cols:
            conn.execute("ALTER TABLE students ADD COLUMN archived_at TEXT")
        if "archive_reason" not in cols:
            conn.execute("ALTER TABLE students ADD COLUMN archive_reason TEXT")
        if "archive_feedback" not in cols:
            conn.execute("ALTER TABLE students ADD COLUMN archive_feedback TEXT")
        if "last_daily_spin" not in cols:
            conn.execute("ALTER TABLE students ADD COLUMN last_daily_spin TEXT")
        if "solve_streak" not in cols:
            conn.execute("ALTER TABLE students ADD COLUMN solve_streak INTEGER DEFAULT 0")
        cols = {row[1] for row in conn.execute("PRAGMA table_info(submissions)").fetchall()}
        if "approved" not in cols:
            conn.execute("ALTER TABLE submissions ADD COLUMN approved INTEGER DEFAULT 0")
        if "bonus_awarded" not in cols:
            conn.execute("ALTER TABLE submissions ADD COLUMN bonus_awarded INTEGER DEFAULT 0")
        if "code_deleted_at" not in cols:
            conn.execute("ALTER TABLE submissions ADD COLUMN code_deleted_at TEXT")
        if "feedback" not in cols:
            conn.execute("ALTER TABLE submissions ADD COLUMN feedback TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_student ON submissions(student_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_task ON submissions(task_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_topic ON tasks(topic_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_topics_module ON topics(module_id)")
        existing = conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
        if existing == 0:
            conn.execute(
                "INSERT INTO modules (module_id, name, order_num, created_at) VALUES (?, ?, ?, ?)",
                ("1", "Основы Python", 1, datetime.now().isoformat())
            )
            conn.execute("UPDATE topics SET module_id = '1' WHERE module_id IS NULL OR module_id = ''")


def cleanup_old_code():
    cutoff = (datetime.now() - timedelta(days=CODE_RETENTION_DAYS)).isoformat()
    with get_db() as conn:
        result = conn.execute(
            """UPDATE submissions 
               SET code = '[удалён]', code_deleted_at = ?
               WHERE submitted_at < ? AND code != '[удалён]' AND code IS NOT NULL""",
            (datetime.now().isoformat(), cutoff)
        )
        return result.rowcount


def is_admin(user_id: int) -> bool:
    with get_db() as conn:
        result = conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone()
        return result is not None


def add_admin(user_id: int) -> bool:
    with get_db() as conn:
        try:
            conn.execute("INSERT INTO admins (user_id, added_at) VALUES (?, ?)", (user_id, datetime.now().isoformat()))
            return True
        except sqlite3.IntegrityError:
            return False


def get_admin_count() -> int:
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]


def create_codes(count: int) -> List[str]:
    codes = []
    with get_db() as conn:
        for _ in range(count):
            while True:
                code = generate_code()
                try:
                    conn.execute("INSERT INTO codes (code, created_at) VALUES (?, ?)", (code, datetime.now().isoformat()))
                    codes.append(code)
                    break
                except sqlite3.IntegrityError:
                    continue
    return codes


def get_unused_codes() -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT code, created_at FROM codes WHERE used_by IS NULL ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def use_code(code: str, user_id: int) -> bool:
    with get_db() as conn:
        result = conn.execute("SELECT id, used_by FROM codes WHERE code = ?", (code.upper(),)).fetchone()
        if not result or result["used_by"] is not None:
            return False
        conn.execute("UPDATE codes SET used_by = ?, used_at = ? WHERE code = ?", (user_id, datetime.now().isoformat(), code.upper()))
        return True


def register_student(user_id: int, username: str, first_name: str, code: str) -> bool:
    if not use_code(code, user_id):
        return False
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO students (user_id, username, first_name, code_used, bonus_points, registered_at) VALUES (?, ?, ?, ?, 0, ?)",
                (user_id, username, first_name, code.upper(), datetime.now().isoformat())
            )
            return True
        except sqlite3.IntegrityError:
            return False


def get_student(user_id: int) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM students WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_student_by_id(student_id: int) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        return dict(row) if row else None


def get_all_students() -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM students ORDER BY registered_at DESC").fetchall()
        return [dict(r) for r in rows]


def is_registered(user_id: int) -> bool:
    return get_student(user_id) is not None


def add_bonus_points(student_id: int, points: int) -> bool:
    with get_db() as conn:
        conn.execute("UPDATE students SET bonus_points = bonus_points + ? WHERE id = ?", (points, student_id))
        return True


def add_module(module_id: str, name: str, order_num: int = 0) -> bool:
    with get_db() as conn:
        try:
            conn.execute("INSERT INTO modules (module_id, name, order_num, created_at) VALUES (?, ?, ?, ?)", (module_id, name, order_num, datetime.now().isoformat()))
            return True
        except sqlite3.IntegrityError:
            return False


def get_modules() -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM modules ORDER BY order_num, module_id").fetchall()
        return [dict(r) for r in rows]


def get_module(module_id: str) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM modules WHERE module_id = ?", (module_id,)).fetchone()
        return dict(row) if row else None


def delete_module(module_id: str) -> bool:
    with get_db() as conn:
        topics = conn.execute("SELECT COUNT(*) FROM topics WHERE module_id = ?", (module_id,)).fetchone()[0]
        if topics > 0:
            return False
        result = conn.execute("DELETE FROM modules WHERE module_id = ?", (module_id,))
        return result.rowcount > 0


def add_topic(topic_id: str, name: str, module_id: str = "1", order_num: int = 0) -> bool:
    with get_db() as conn:
        try:
            conn.execute("INSERT INTO topics (topic_id, module_id, name, order_num, created_at) VALUES (?, ?, ?, ?, ?)", (topic_id, module_id, name, order_num, datetime.now().isoformat()))
            return True
        except sqlite3.IntegrityError:
            return False


def get_topics() -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM topics ORDER BY module_id, order_num, topic_id").fetchall()
        return [dict(r) for r in rows]


def get_topics_by_module(module_id: str) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM topics WHERE module_id = ? ORDER BY order_num, topic_id", (module_id,)).fetchall()
        return [dict(r) for r in rows]


def get_topic(topic_id: str) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM topics WHERE topic_id = ?", (topic_id,)).fetchone()
        return dict(row) if row else None


def delete_topic(topic_id: str) -> bool:
    with get_db() as conn:
        tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE topic_id = ?", (topic_id,)).fetchone()[0]
        if tasks > 0:
            return False
        result = conn.execute("DELETE FROM topics WHERE topic_id = ?", (topic_id,))
        return result.rowcount > 0


def add_task(task_id: str, topic_id: str, title: str, description: str, test_code: str) -> bool:
    with get_db() as conn:
        try:
            conn.execute("INSERT INTO tasks (task_id, topic_id, title, description, test_code, created_at) VALUES (?, ?, ?, ?, ?, ?)", (task_id, topic_id, title, description, test_code, datetime.now().isoformat()))
            return True
        except sqlite3.IntegrityError:
            return False


def get_task(task_id: str) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def get_tasks_by_topic(topic_id: str) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks WHERE topic_id = ? ORDER BY task_id", (topic_id,)).fetchall()
        return [dict(r) for r in rows]


def get_all_tasks() -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY topic_id, task_id").fetchall()
        return [dict(r) for r in rows]


def delete_task(task_id: str) -> bool:
    with get_db() as conn:
        result = conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        return result.rowcount > 0


def add_submission(student_id: int, task_id: str, code: str, passed: bool, output: str) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO submissions (student_id, task_id, code, passed, output, submitted_at) VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, task_id, code, int(passed), output[:5000], datetime.now().isoformat())
        )
        return cursor.lastrowid


def get_student_submissions(student_id: int, task_id: str = None) -> List[Dict]:
    with get_db() as conn:
        if task_id:
            rows = conn.execute("SELECT * FROM submissions WHERE student_id = ? AND task_id = ? ORDER BY submitted_at DESC", (student_id, task_id)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM submissions WHERE student_id = ? ORDER BY submitted_at DESC", (student_id,)).fetchall()
        return [dict(r) for r in rows]


def get_recent_submissions(student_id: int, limit: int = 10) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM submissions WHERE student_id = ? ORDER BY submitted_at DESC LIMIT ?", (student_id, limit)).fetchall()
        return [dict(r) for r in rows]


def get_submission_by_id(submission_id: int) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        return dict(row) if row else None


def delete_submission(submission_id: int) -> bool:
    with get_db() as conn:
        sub = conn.execute("SELECT student_id, approved, bonus_awarded FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        if sub and sub["approved"]:
            conn.execute("UPDATE students SET bonus_points = bonus_points - ? WHERE id = ?", (sub["bonus_awarded"], sub["student_id"]))
        result = conn.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))
        return result.rowcount > 0


def has_solved(student_id: int, task_id: str) -> bool:
    with get_db() as conn:
        result = conn.execute("SELECT 1 FROM submissions WHERE student_id = ? AND task_id = ? AND passed = 1", (student_id, task_id)).fetchone()
        return result is not None


def approve_submission(submission_id: int, bonus_points: int = 1) -> bool:
    with get_db() as conn:
        sub = conn.execute("SELECT student_id, approved FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        if not sub or sub["approved"]:
            return False
        conn.execute("UPDATE submissions SET approved = 1, bonus_awarded = ? WHERE id = ?", (bonus_points, submission_id))
        conn.execute("UPDATE students SET bonus_points = bonus_points + ? WHERE id = ?", (bonus_points, sub["student_id"]))
        return True


def unapprove_submission(submission_id: int) -> bool:
    with get_db() as conn:
        sub = conn.execute("SELECT student_id, approved, bonus_awarded FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        if not sub or not sub["approved"]:
            return False
        conn.execute("UPDATE submissions SET approved = 0 WHERE id = ?", (submission_id,))
        conn.execute("UPDATE students SET bonus_points = bonus_points - ? WHERE id = ?", (sub["bonus_awarded"], sub["student_id"]))
        return True


def set_feedback(submission_id: int, feedback: str) -> bool:
    with get_db() as conn:
        conn.execute("UPDATE submissions SET feedback = ? WHERE id = ?", (feedback, submission_id))
        return True


def get_student_stats(student_id: int) -> Dict:
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM submissions WHERE student_id = ?", (student_id,)).fetchone()[0]
        solved = conn.execute("SELECT COUNT(DISTINCT task_id) FROM submissions WHERE student_id = ? AND passed = 1", (student_id,)).fetchone()[0]
        total_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        bonus = conn.execute("SELECT bonus_points FROM students WHERE id = ?", (student_id,)).fetchone()
        bonus_points = bonus[0] if bonus else 0
        approved = conn.execute("SELECT COUNT(*) FROM submissions WHERE student_id = ? AND approved = 1", (student_id,)).fetchone()[0]
        return {
            "total_submissions": total,
            "solved_tasks": solved,
            "total_tasks": total_tasks,
            "bonus_points": bonus_points,
            "approved_count": approved
        }


def get_all_students_stats() -> List[Dict]:
    students = get_all_students()
    result = []
    for student in students:
        stats = get_student_stats(student["id"])
        result.append({**student, **stats})
    return result


def get_leaderboard(limit: int = 20) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute("""
            SELECT 
                s.id, s.user_id, s.username, s.first_name, s.bonus_points,
                COUNT(DISTINCT CASE WHEN sub.passed = 1 THEN sub.task_id END) as solved,
                (SELECT COUNT(*) FROM tasks) as total_tasks
            FROM students s
            LEFT JOIN submissions sub ON s.id = sub.student_id
            GROUP BY s.id
            ORDER BY (COUNT(DISTINCT CASE WHEN sub.passed = 1 THEN sub.task_id END) + s.bonus_points) DESC, s.registered_at ASC
            LIMIT ?
        """, (limit,)).fetchall()
        result = []
        for i, row in enumerate(rows, 1):
            r = dict(row)
            r["rank"] = i
            r["score"] = r["solved"] + r["bonus_points"]
            result.append(r)
        return result


def assign_task(student_id: int, task_id: str) -> bool:
    with get_db() as conn:
        try:
            conn.execute("INSERT INTO assigned_tasks (student_id, task_id, assigned_at) VALUES (?, ?, ?)", (student_id, task_id, datetime.now().isoformat()))
            return True
        except sqlite3.IntegrityError:
            return False


def unassign_task(student_id: int, task_id: str) -> bool:
    with get_db() as conn:
        result = conn.execute("DELETE FROM assigned_tasks WHERE student_id = ? AND task_id = ?", (student_id, task_id))
        return result.rowcount > 0


def get_assigned_tasks(student_id: int) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute("""
            SELECT t.*, a.assigned_at 
            FROM assigned_tasks a 
            JOIN tasks t ON a.task_id = t.task_id 
            WHERE a.student_id = ? 
            ORDER BY a.assigned_at DESC
        """, (student_id,)).fetchall()
        return [dict(r) for r in rows]


def is_task_assigned(student_id: int, task_id: str) -> bool:
    with get_db() as conn:
        result = conn.execute("SELECT 1 FROM assigned_tasks WHERE student_id = ? AND task_id = ?", (student_id, task_id)).fetchone()
        return result is not None


def update_student_name(student_id: int, new_name: str) -> bool:
    with get_db() as conn:
        conn.execute("UPDATE students SET first_name = ? WHERE id = ?", (new_name, student_id))
        return True


def delete_student(student_id: int) -> bool:
    with get_db() as conn:
        conn.execute("DELETE FROM assigned_tasks WHERE student_id = ?", (student_id,))
        conn.execute("DELETE FROM submissions WHERE student_id = ?", (student_id,))
        result = conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
        return result.rowcount > 0


def archive_student(student_id: int, reason: str, feedback: str) -> bool:
    """Archives student with a reason (e.g. HIRED) and feedback"""
    with get_db() as conn:
        # Add archived_at and archive columns if not exist
        cols = {row[1] for row in conn.execute("PRAGMA table_info(students)").fetchall()}
        if "archived_at" not in cols:
            conn.execute("ALTER TABLE students ADD COLUMN archived_at TEXT")
        if "archive_reason" not in cols:
            conn.execute("ALTER TABLE students ADD COLUMN archive_reason TEXT")
        if "archive_feedback" not in cols:
            conn.execute("ALTER TABLE students ADD COLUMN archive_feedback TEXT")
        
        conn.execute(
            "UPDATE students SET archived_at = ?, archive_reason = ?, archive_feedback = ? WHERE id = ?",
            (datetime.now().isoformat(), reason, feedback, student_id)
        )
        return True


def get_archived_students() -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM students WHERE archived_at IS NOT NULL ORDER BY archived_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_active_students() -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM students WHERE archived_at IS NULL ORDER BY registered_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_active_students_stats() -> List[Dict]:
    students = get_active_students()
    result = []
    for student in students:
        stats = get_student_stats(student["id"])
        result.append({**student, **stats})
    return result


# === GAMBLING FUNCTIONS ===

def can_spin_daily(student_id: int) -> bool:
    """Check if student can use daily roulette"""
    with get_db() as conn:
        row = conn.execute("SELECT last_daily_spin FROM students WHERE id = ?", (student_id,)).fetchone()
        if not row or not row["last_daily_spin"]:
            return True
        last_spin = datetime.fromisoformat(row["last_daily_spin"])
        today = datetime.now().date()
        return last_spin.date() < today


def do_daily_spin(student_id: int) -> int:
    """Do daily spin, returns points won (can be negative)"""
    import random
    with get_db() as conn:
        # 50% → +1, 25% → +2, 15% → 0, 10% → -1
        roll = random.randint(1, 100)
        if roll <= 50:
            points = 1
        elif roll <= 75:
            points = 2
        elif roll <= 90:
            points = 0
        else:
            points = -1
        
        conn.execute("UPDATE students SET last_daily_spin = ? WHERE id = ?", 
                     (datetime.now().isoformat(), student_id))
        if points != 0:
            conn.execute("UPDATE students SET bonus_points = MAX(0, bonus_points + ?) WHERE id = ?", 
                         (points, student_id))
        return points


def get_solve_streak(student_id: int) -> int:
    """Get current solve streak"""
    with get_db() as conn:
        row = conn.execute("SELECT solve_streak FROM students WHERE id = ?", (student_id,)).fetchone()
        return row["solve_streak"] if row and row["solve_streak"] else 0


def increment_streak(student_id: int) -> int:
    """Increment streak and return new value"""
    with get_db() as conn:
        conn.execute("UPDATE students SET solve_streak = COALESCE(solve_streak, 0) + 1 WHERE id = ?", (student_id,))
        row = conn.execute("SELECT solve_streak FROM students WHERE id = ?", (student_id,)).fetchone()
        return row["solve_streak"] if row else 1


def reset_streak(student_id: int):
    """Reset streak to 0"""
    with get_db() as conn:
        conn.execute("UPDATE students SET solve_streak = 0 WHERE id = ?", (student_id,))


def open_chest() -> int:
    """Open chest, returns random bonus 1-5"""
    import random
    return random.randint(1, 5)


def gamble_points(student_id: int, amount: int) -> tuple[bool, int]:
    """50/50 gamble - double or lose. Returns (won, new_balance)"""
    import random
    with get_db() as conn:
        row = conn.execute("SELECT bonus_points FROM students WHERE id = ?", (student_id,)).fetchone()
        current = row["bonus_points"] if row else 0
        
        if current < amount:
            return False, current
        
        won = random.choice([True, False])
        if won:
            change = amount  # win = +amount (so total is doubled)
        else:
            change = -amount  # lose the bet
        
        conn.execute("UPDATE students SET bonus_points = MAX(0, bonus_points + ?) WHERE id = ?", 
                     (change, student_id))
        return won, current + change


init_db()