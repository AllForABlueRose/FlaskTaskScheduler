import threading
import time as _time
from datetime import datetime

from db import db_connect
from recurrence import ensure_range_materialized, needs_daily_check


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
    slot_key = f'{now.date().isoformat()}-{now.hour}-{quarter}'

    with db_connect() as conn:
        if needs_daily_check(conn, now.date()):
            try:
                ensure_range_materialized(conn, now.date())
            except Exception as e:
                print(f'[scheduler] materialization error: {e}', flush=True)

        rows = conn.execute(
            '''SELECT s.id, s.slot, s.last_run_at, s.input AS row_input,
                      t.code, t.name, t.input AS task_input
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
            input_text = row['row_input'] if row['row_input'] is not None else row['task_input']
            to_run.append((row['name'], row['code'], input_text))

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
