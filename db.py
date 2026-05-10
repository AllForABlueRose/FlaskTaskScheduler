import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

DB = 'scheduler.db'


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
                last_run_at TEXT
            )
        ''')

    conn.commit()
    conn.close()
