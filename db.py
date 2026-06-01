import sqlite3
from contextlib import contextmanager
from datetime import datetime

from werkzeug.security import generate_password_hash

DB = 'scheduler.db'


@contextmanager
def db_connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            session_token TEXT
        )
    ''')

    user_cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
    if 'session_token' not in user_cols:
        c.execute("ALTER TABLE users ADD COLUMN session_token TEXT")

    admin_exists = c.execute(
        "SELECT 1 FROM users WHERE role='admin' LIMIT 1"
    ).fetchone()
    if not admin_exists:
        c.execute(
            'INSERT INTO users (username, password_hash, role, status, created_at) VALUES (?, ?, ?, ?, ?)',
            ('admin', generate_password_hash('admin'), 'admin', 'active', datetime.utcnow().isoformat())
        )

    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks(
            id TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            tags TEXT,
            color TEXT,
            code TEXT
        )
    ''')

    task_cols = [r[1] for r in c.execute("PRAGMA table_info(tasks)").fetchall()]
    if 'input' not in task_cols:
        c.execute("ALTER TABLE tasks ADD COLUMN input TEXT DEFAULT ''")
    if 'recurrence' not in task_cols:
        c.execute("ALTER TABLE tasks ADD COLUMN recurrence TEXT")

    schedule_exists = c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schedule'"
    ).fetchone()

    cols = []
    if schedule_exists:
        cols = [r[1] for r in c.execute("PRAGMA table_info(schedule)").fetchall()]

    if schedule_exists and 'id' not in cols:
        old_rows = c.execute(
            'SELECT slot, task_id, COALESCE(duration, 1) FROM schedule'
        ).fetchall()
        c.execute('DROP TABLE schedule')
        c.execute('''
            CREATE TABLE schedule(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot TEXT NOT NULL,
                task_id TEXT,
                duration INTEGER DEFAULT 1,
                last_run_at TEXT
            )
        ''')
        for slot, task_id, duration in old_rows:
            new_slot = f'{slot}-0'
            new_duration = (duration or 1) * 4
            c.execute(
                'INSERT INTO schedule (slot, task_id, duration) VALUES (?, ?, ?)',
                (new_slot, task_id, new_duration)
            )
    elif not schedule_exists:
        c.execute('''
            CREATE TABLE schedule(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot TEXT NOT NULL,
                task_id TEXT,
                duration INTEGER DEFAULT 1,
                last_run_at TEXT,
                is_recurring INTEGER DEFAULT 0,
                input TEXT
            )
        ''')

    schedule_cols = [r[1] for r in c.execute("PRAGMA table_info(schedule)").fetchall()]
    if 'is_recurring' not in schedule_cols:
        c.execute("ALTER TABLE schedule ADD COLUMN is_recurring INTEGER DEFAULT 0")
    if 'input' not in schedule_cols:
        c.execute("ALTER TABLE schedule ADD COLUMN input TEXT")

    c.execute('''
        CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS events(
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            category TEXT,
            color TEXT,
            description TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_end ON events(end_date)')

    c.execute('''
        CREATE TABLE IF NOT EXISTS app_file_status(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder TEXT NOT NULL,
            filename TEXT NOT NULL,
            status TEXT NOT NULL,
            file_mtime TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_app_file_status_folder ON app_file_status(folder)')

    afs_cols = [r[1] for r in c.execute("PRAGMA table_info(app_file_status)").fetchall()]
    if 'approved_path' not in afs_cols:
        c.execute("ALTER TABLE app_file_status ADD COLUMN approved_path TEXT")

    c.execute('''
        CREATE TABLE IF NOT EXISTS assignments(
            id TEXT PRIMARY KEY,
            project_code TEXT NOT NULL,
            title TEXT NOT NULL,
            color TEXT,
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS timeline_schedule(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot TEXT NOT NULL,
            assignment_id TEXT,
            duration INTEGER DEFAULT 1
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_timeline_slot ON timeline_schedule(slot)')

    c.execute('''
        CREATE TABLE IF NOT EXISTS timeline_sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_date TEXT NOT NULL,
            started_at TEXT NOT NULL,
            stopped_at TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_timeline_session_date ON timeline_sessions(session_date)')

    c.execute('''
        CREATE TABLE IF NOT EXISTS timeline_marks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            marked_at TEXT NOT NULL,
            sort_order INTEGER NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS timeline_segments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            segment_index INTEGER NOT NULL,
            assignment_id TEXT
        )
    ''')

    conn.commit()
    conn.close()
