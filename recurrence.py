import json
from calendar import monthrange
from datetime import date, timedelta


_PY_TO_JS_DOW = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}


def to_js_dow(d):
    return _PY_TO_JS_DOW[d.weekday()]


def nth_of_weekday(d):
    return (d.day - 1) // 7 + 1


def is_last_weekday_of_month(d):
    return (d + timedelta(days=7)).month != d.month


def monday_of(d):
    return d - timedelta(days=d.weekday())


def matches(rec, d):
    if not rec:
        return False
    dow = to_js_dow(d)
    t = rec.get('type')

    if t == 'daily':
        return True
    if t == 'weekday':
        return d.weekday() < 5
    if t == 'weekly':
        return dow in (rec.get('daysOfWeek') or [])
    if t == 'monthly':
        if rec.get('monthlyMode') == 'weekday':
            if dow != rec.get('nthWeekday'):
                return False
            nth = rec.get('nth')
            return is_last_weekday_of_month(d) if nth == -1 else nth_of_weekday(d) == nth
        return d.day == (rec.get('dayOfMonth') or 1)
    if t == 'custom':
        return _matches_custom(rec, d, dow)
    return False


def _matches_custom(rec, d, dow):
    interval = max(1, rec.get('interval') or 1)
    start_str = rec.get('startDate')
    try:
        start = date.fromisoformat(start_str) if start_str else d
    except ValueError:
        start = d
    if d < start:
        return False
    unit = rec.get('unit')

    if unit == 'days':
        return (d - start).days % interval == 0

    if unit == 'weeks':
        if dow not in (rec.get('daysOfWeek') or []):
            return False
        weeks = (monday_of(d) - monday_of(start)).days // 7
        return weeks % interval == 0

    if unit == 'months':
        diff = (d.year - start.year) * 12 + (d.month - start.month)
        if diff < 0 or diff % interval != 0:
            return False
        if rec.get('monthlyMode') == 'weekday':
            if dow != rec.get('nthWeekday'):
                return False
            nth = rec.get('nth')
            return is_last_weekday_of_month(d) if nth == -1 else nth_of_weekday(d) == nth
        return d.day == (rec.get('dayOfMonth') or 1)

    return False


def time_to_hour_quarter(time_str):
    if not time_str:
        return 9, 0
    try:
        parts = time_str.split(':')
        hour = int(parts[0]) % 24
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return 9, 0
    return hour, max(0, min(3, minute // 15))


def duration_quarters(rec):
    dur = rec.get('duration') or 60
    try:
        dur = int(dur)
    except (TypeError, ValueError):
        dur = 60
    return max(1, round(dur / 15))


def slot_key(d, hour, quarter):
    return f'{d.isoformat()}-{hour}-{quarter}'


def parse_recurrence(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return None


def generate_entries(rec, start, end):
    if not rec:
        return
    hour, quarter = time_to_hour_quarter(rec.get('time'))
    dur = duration_quarters(rec)
    d = start
    while d <= end:
        if matches(rec, d):
            yield slot_key(d, hour, quarter), dur
        d += timedelta(days=1)


def first_day_of_next_month(d):
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def last_day_of_month(d):
    return date(d.year, d.month, monthrange(d.year, d.month)[1])


def is_last_week_of_month(today):
    return (last_day_of_month(today) - today).days < 7


def valid_range(today):
    start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month_first = first_day_of_next_month(today)
    end = last_day_of_month(next_month_first)
    if is_last_week_of_month(today):
        end = last_day_of_month(first_day_of_next_month(next_month_first))
    return start, end


def materialize_task(conn, task_id, rec, start, end):
    rec = parse_recurrence(rec)
    if not rec:
        return
    range_lo = start.isoformat()
    range_hi = (end + timedelta(days=1)).isoformat()

    preserved = {
        row[0]: row[1]
        for row in conn.execute(
            'SELECT slot, input FROM schedule '
            'WHERE task_id=? AND is_recurring=1 AND slot >= ? AND slot < ? AND input IS NOT NULL',
            (task_id, range_lo, range_hi)
        ).fetchall()
    }

    conn.execute(
        'DELETE FROM schedule WHERE task_id=? AND is_recurring=1 AND slot >= ? AND slot < ?',
        (task_id, range_lo, range_hi)
    )
    for slot, dur in generate_entries(rec, start, end):
        existing = conn.execute(
            'SELECT id FROM schedule WHERE task_id=? AND slot=? LIMIT 1',
            (task_id, slot)
        ).fetchone()
        if existing:
            conn.execute(
                'UPDATE schedule SET is_recurring=1, duration=?, last_run_at=NULL WHERE id=?',
                (dur, existing[0])
            )
        else:
            conn.execute(
                'INSERT INTO schedule (slot, task_id, duration, is_recurring, input) '
                'VALUES (?, ?, ?, 1, ?)',
                (slot, task_id, dur, preserved.get(slot))
            )


def detach_recurring_entries(conn, task_id):
    conn.execute(
        'UPDATE schedule SET is_recurring=0 WHERE task_id=? AND is_recurring=1',
        (task_id,)
    )


def ensure_range_materialized(conn, today):
    start, end = valid_range(today)
    cur = conn.execute("SELECT value FROM meta WHERE key='last_materialization_through'")
    row = cur.fetchone()
    last_through = None
    if row and row[0]:
        try:
            last_through = date.fromisoformat(row[0])
        except ValueError:
            last_through = None

    if last_through and last_through >= end:
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_materialization_date', ?)",
            (today.isoformat(),)
        )
        return start, end, False

    gap_start = last_through + timedelta(days=1) if last_through else start
    if gap_start < start:
        gap_start = start

    rows = conn.execute(
        "SELECT id, recurrence FROM tasks WHERE recurrence IS NOT NULL"
    ).fetchall()
    for r in rows:
        task_id, rec_json = r[0], r[1]
        materialize_task(conn, task_id, rec_json, gap_start, end)

    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_materialization_through', ?)",
        (end.isoformat(),)
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_materialization_date', ?)",
        (today.isoformat(),)
    )
    return start, end, True


def needs_daily_check(conn, today):
    row = conn.execute("SELECT value FROM meta WHERE key='last_materialization_date'").fetchone()
    if not row or not row[0]:
        return True
    return row[0] != today.isoformat()
