import sqlite3
import threading
import time as _time
from datetime import datetime

from db import DB


def parse_input(text):
    if not text or not text.strip():
        return []
    if '\n' in text:
        parts = text.splitlines()
    elif ',' in text:
        parts = text.split(',')
    else:
        parts = [text]
    return [p.strip() for p in parts if p.strip()]


def run_task(name, code, slot_key, input_text=None):
    print(f'[scheduler] running: {name} ({slot_key})', flush=True)
    if not code:
        return

    values = parse_input(input_text)
    if not values:
        try:
            exec(code, {'__name__': '__main__'})
        except Exception as e:
            print(f'[scheduler] task failed ({name}): {e}', flush=True)
        return

    for v in values:
        try:
            exec(code, {'__name__': '__main__', 'value': v})
        except Exception as e:
            print(f'[scheduler] task failed ({name}, value={v!r}): {e}', flush=True)


def tick_scheduler():
    now = datetime.now()
    quarter = now.minute // 15
    quarter_start = now.replace(minute=quarter * 15, second=0, microsecond=0)
    slot_key = now.strftime('%a %m/%d') + f'-{now.hour}-{quarter}'

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        '''SELECT s.id, s.slot, s.last_run_at, t.code, t.name, t.input
           FROM schedule s JOIN tasks t ON t.id = s.task_id
           WHERE s.slot = ?''',
        (slot_key,)
    ).fetchall()

    to_run = []
    for row in rows:
        if row['last_run_at'] and row['last_run_at'] >= quarter_start.isoformat():
            continue
        conn.execute(
            'UPDATE schedule SET last_run_at=? WHERE id=?',
            (now.isoformat(), row['id'])
        )
        to_run.append((row['name'], row['code'], row['input']))

    conn.commit()
    conn.close()

    for name, code, input_text in to_run:
        threading.Thread(
            target=run_task,
            args=(name, code, slot_key, input_text),
            daemon=True,
        ).start()


def run_scheduler():
    while True:
        try:
            tick_scheduler()
        except Exception as e:
            print(f'[scheduler] tick error: {e}', flush=True)
        _time.sleep(30)
