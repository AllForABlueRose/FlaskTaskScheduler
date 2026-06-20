import uuid
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from db import db_connect
from routes.auth import login_required

timeline_bp = Blueprint('timeline', __name__)

# A mark cannot be dragged closer than this to either neighbouring anchor, so the
# segments before and after it never collapse below a usable length. Mirrors
# STRIP_MIN_SEGMENT_MS on the client.
STRIP_MIN_SEGMENT = timedelta(minutes=1)


@timeline_bp.route('/api/timeline/assignments')
@login_required
def list_assignments():
    with db_connect() as conn:
        rows = conn.execute('SELECT * FROM assignments ORDER BY created_at DESC').fetchall()
    return jsonify([dict(r) for r in rows])


@timeline_bp.route('/api/timeline/assignment', methods=['POST'])
@login_required
def create_assignment():
    data = request.json or {}
    project_code = (data.get('project_code') or '').strip()
    title = (data.get('title') or '').strip()
    color = (data.get('color') or '#64748b').strip()
    if not project_code or not title:
        return jsonify({'error': 'project_code and title required'}), 400
    aid = str(uuid.uuid4())
    with db_connect() as conn:
        conn.execute(
            'INSERT INTO assignments (id, project_code, title, color, created_at) VALUES (?, ?, ?, ?, ?)',
            (aid, project_code, title, color, datetime.now().isoformat())
        )
    return jsonify({'id': aid})


@timeline_bp.route('/api/timeline/assignment/<aid>', methods=['PUT'])
@login_required
def update_assignment(aid):
    data = request.json or {}
    project_code = (data.get('project_code') or '').strip()
    title = (data.get('title') or '').strip()
    color = (data.get('color') or '#64748b').strip()
    if not project_code or not title:
        return jsonify({'error': 'project_code and title required'}), 400
    with db_connect() as conn:
        conn.execute(
            'UPDATE assignments SET project_code=?, title=?, color=? WHERE id=?',
            (project_code, title, color, aid)
        )
    return jsonify({'ok': True})


@timeline_bp.route('/api/timeline/assignment/<aid>', methods=['DELETE'])
@login_required
def delete_assignment(aid):
    with db_connect() as conn:
        conn.execute('DELETE FROM timeline_schedule WHERE assignment_id=?', (aid,))
        conn.execute('DELETE FROM assignments WHERE id=?', (aid,))
    return jsonify({'ok': True})


@timeline_bp.route('/api/timeline/schedule')
@login_required
def get_schedule():
    with db_connect() as conn:
        rows = conn.execute(
            'SELECT id, slot, assignment_id, duration FROM timeline_schedule ORDER BY slot'
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@timeline_bp.route('/api/timeline/schedule', methods=['POST'])
@login_required
def set_schedule():
    data = request.json or {}
    slot = (data.get('slot') or '').strip()
    assignment_id = (data.get('assignment_id') or '').strip()
    duration = data.get('duration', 1)
    if not slot or not assignment_id:
        return jsonify({'error': 'slot and assignment_id required'}), 400
    with db_connect() as conn:
        existing = conn.execute(
            'SELECT id FROM timeline_schedule WHERE slot=?', (slot,)
        ).fetchone()
        if existing:
            conn.execute(
                'UPDATE timeline_schedule SET assignment_id=?, duration=? WHERE id=?',
                (assignment_id, duration, existing['id'])
            )
        else:
            conn.execute(
                'INSERT INTO timeline_schedule (slot, assignment_id, duration) VALUES (?, ?, ?)',
                (slot, assignment_id, duration)
            )
    return jsonify({'ok': True})


@timeline_bp.route('/api/timeline/schedule/remove', methods=['POST'])
@login_required
def remove_schedule():
    data = request.json or {}
    slot = (data.get('slot') or '').strip()
    if not slot:
        return jsonify({'error': 'slot required'}), 400
    with db_connect() as conn:
        conn.execute('DELETE FROM timeline_schedule WHERE slot=?', (slot,))
    return jsonify({'ok': True})


@timeline_bp.route('/api/timeline/strip/today')
@login_required
def strip_today():
    today = datetime.now().strftime('%Y-%m-%d')
    with db_connect() as conn:
        session = conn.execute(
            'SELECT * FROM timeline_sessions WHERE session_date=? ORDER BY id DESC LIMIT 1',
            (today,)
        ).fetchone()
        if not session:
            return jsonify({'session': None, 'marks': [], 'segments': []})
        sid = session['id']
        marks = conn.execute(
            'SELECT * FROM timeline_marks WHERE session_id=? ORDER BY sort_order', (sid,)
        ).fetchall()
        segments = conn.execute(
            'SELECT * FROM timeline_segments WHERE session_id=? ORDER BY segment_index', (sid,)
        ).fetchall()
    return jsonify({
        'session': dict(session),
        'marks': [dict(m) for m in marks],
        'segments': [dict(s) for s in segments],
    })


@timeline_bp.route('/api/timeline/strip/start', methods=['POST'])
@login_required
def strip_start():
    today = datetime.now().strftime('%Y-%m-%d')
    now_iso = datetime.now().isoformat()
    with db_connect() as conn:
        existing = conn.execute(
            'SELECT id FROM timeline_sessions WHERE session_date=? AND stopped_at IS NULL', (today,)
        ).fetchone()
        if existing:
            return jsonify({'error': 'session already active today'}), 409
        cur = conn.execute(
            'INSERT INTO timeline_sessions (session_date, started_at, stopped_at, created_at) VALUES (?, ?, NULL, ?)',
            (today, now_iso, now_iso)
        )
        sid = cur.lastrowid
        conn.execute(
            'INSERT INTO timeline_segments (session_id, segment_index, assignment_id) VALUES (?, 0, NULL)',
            (sid,)
        )
        session = conn.execute('SELECT * FROM timeline_sessions WHERE id=?', (sid,)).fetchone()
        segments = conn.execute('SELECT * FROM timeline_segments WHERE session_id=?', (sid,)).fetchall()
    return jsonify({
        'session': dict(session),
        'marks': [],
        'segments': [dict(s) for s in segments],
    })


@timeline_bp.route('/api/timeline/strip/mark', methods=['POST'])
@login_required
def strip_mark():
    data = request.json or {}
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({'error': 'session_id required'}), 400
    now_iso = datetime.now().isoformat()
    with db_connect() as conn:
        session = conn.execute(
            'SELECT * FROM timeline_sessions WHERE id=? AND stopped_at IS NULL', (session_id,)
        ).fetchone()
        if not session:
            return jsonify({'error': 'no active session'}), 404
        mark_count = conn.execute(
            'SELECT COUNT(*) as cnt FROM timeline_marks WHERE session_id=?', (session_id,)
        ).fetchone()['cnt']
        conn.execute(
            'INSERT INTO timeline_marks (session_id, marked_at, sort_order) VALUES (?, ?, ?)',
            (session_id, now_iso, mark_count)
        )
        new_seg_index = mark_count + 1
        conn.execute(
            'INSERT INTO timeline_segments (session_id, segment_index, assignment_id) VALUES (?, ?, NULL)',
            (session_id, new_seg_index)
        )
        marks = conn.execute(
            'SELECT * FROM timeline_marks WHERE session_id=? ORDER BY sort_order', (session_id,)
        ).fetchall()
        segments = conn.execute(
            'SELECT * FROM timeline_segments WHERE session_id=? ORDER BY segment_index', (session_id,)
        ).fetchall()
    return jsonify({
        'marks': [dict(m) for m in marks],
        'segments': [dict(s) for s in segments],
    })


@timeline_bp.route('/api/timeline/strip/stop', methods=['POST'])
@login_required
def strip_stop():
    data = request.json or {}
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({'error': 'session_id required'}), 400
    now_iso = datetime.now().isoformat()
    with db_connect() as conn:
        session = conn.execute(
            'SELECT * FROM timeline_sessions WHERE id=?', (session_id,)
        ).fetchone()
        if not session:
            return jsonify({'error': 'session not found'}), 404
        # First red press freezes the strip: stamp stopped_at so the end point
        # stops progressing with wall-clock time. Recording onto the week grid is
        # a separate gate (finalized=1) that requires every segment assigned.
        if session['stopped_at'] is None:
            conn.execute(
                'UPDATE timeline_sessions SET stopped_at=? WHERE id=?', (now_iso, session_id)
            )
        segments = conn.execute(
            'SELECT segment_index, assignment_id FROM timeline_segments WHERE session_id=? '
            'ORDER BY segment_index', (session_id,)
        ).fetchall()
        unassigned = [s['segment_index'] for s in segments if not s['assignment_id']]
        if not unassigned and not session['finalized']:
            conn.execute(
                'UPDATE timeline_sessions SET finalized=1 WHERE id=?', (session_id,)
            )
        session = conn.execute('SELECT * FROM timeline_sessions WHERE id=?', (session_id,)).fetchone()
    return jsonify({'session': dict(session), 'unassigned': unassigned})


@timeline_bp.route('/api/timeline/strip/finalized')
@login_required
def strip_finalized():
    with db_connect() as conn:
        sessions = conn.execute(
            'SELECT * FROM timeline_sessions WHERE finalized=1 AND stopped_at IS NOT NULL '
            'ORDER BY id'
        ).fetchall()
        result = []
        for s in sessions:
            sid = s['id']
            marks = conn.execute(
                'SELECT * FROM timeline_marks WHERE session_id=? ORDER BY sort_order', (sid,)
            ).fetchall()
            segments = conn.execute(
                'SELECT * FROM timeline_segments WHERE session_id=? ORDER BY segment_index', (sid,)
            ).fetchall()
            result.append({
                'session': dict(s),
                'marks': [dict(m) for m in marks],
                'segments': [dict(seg) for seg in segments],
            })
    return jsonify(result)


@timeline_bp.route('/api/timeline/strip/mark/update', methods=['POST'])
@login_required
def strip_mark_update():
    data = request.json or {}
    mark_id = data.get('mark_id')
    marked_at = (data.get('marked_at') or '').strip()
    if not mark_id or not marked_at:
        return jsonify({'error': 'mark_id and marked_at required'}), 400
    with db_connect() as conn:
        row = conn.execute(
            'SELECT m.id, m.session_id, m.sort_order, s.started_at, s.stopped_at '
            'FROM timeline_marks m JOIN timeline_sessions s ON s.id = m.session_id '
            'WHERE m.id=?', (mark_id,)
        ).fetchone()
        if not row:
            return jsonify({'error': 'mark not found'}), 404
        # Enforce the ordering + minimum-gap invariant on the server too: the new
        # time must lie between the prev and next anchor points (start, neighbouring
        # marks, or stopped_at / now), keeping at least STRIP_MIN_SEGMENT on each
        # side when the gap is wide enough to allow it.
        try:
            new_ts = datetime.fromisoformat(marked_at)
        except ValueError:
            return jsonify({'error': 'invalid marked_at'}), 400
        prev = conn.execute(
            'SELECT marked_at FROM timeline_marks WHERE session_id=? AND sort_order<? '
            'ORDER BY sort_order DESC LIMIT 1', (row['session_id'], row['sort_order'])
        ).fetchone()
        prev_ts = datetime.fromisoformat(prev['marked_at']) if prev else datetime.fromisoformat(row['started_at'])
        next_row = conn.execute(
            'SELECT marked_at FROM timeline_marks WHERE session_id=? AND sort_order>? '
            'ORDER BY sort_order ASC LIMIT 1', (row['session_id'], row['sort_order'])
        ).fetchone()
        if next_row:
            next_ts = datetime.fromisoformat(next_row['marked_at'])
        elif row['stopped_at']:
            next_ts = datetime.fromisoformat(row['stopped_at'])
        else:
            next_ts = datetime.now()
        if next_ts - prev_ts > 2 * STRIP_MIN_SEGMENT:
            lo, hi = prev_ts + STRIP_MIN_SEGMENT, next_ts - STRIP_MIN_SEGMENT
        else:
            lo, hi = prev_ts, next_ts  # gap too tight to honour the minimum on both sides
        if not (lo <= new_ts <= hi):
            return jsonify({'error': 'marked_at outside neighbour bounds'}), 400
        conn.execute(
            'UPDATE timeline_marks SET marked_at=? WHERE id=?',
            (marked_at, mark_id)
        )
        # Adjusting a point is a tamper signal: straighten the segments immediately
        # before and after it so the record visibly records that the point moved.
        # Segment i spans points[i]..points[i+1]; this mark is point sort_order+1,
        # so its neighbours are segment_index sort_order and sort_order+1.
        conn.execute(
            'UPDATE timeline_segments SET straightened=1 '
            'WHERE session_id=? AND segment_index IN (?, ?)',
            (row['session_id'], row['sort_order'], row['sort_order'] + 1)
        )
        segments = conn.execute(
            'SELECT * FROM timeline_segments WHERE session_id=? ORDER BY segment_index',
            (row['session_id'],)
        ).fetchall()
    return jsonify({'ok': True, 'segments': [dict(s) for s in segments]})


@timeline_bp.route('/api/timeline/strip/segment/assign', methods=['POST'])
@login_required
def strip_segment_assign():
    data = request.json or {}
    segment_id = data.get('segment_id')
    assignment_id = (data.get('assignment_id') or '').strip()
    if not segment_id or not assignment_id:
        return jsonify({'error': 'segment_id and assignment_id required'}), 400
    with db_connect() as conn:
        conn.execute(
            'UPDATE timeline_segments SET assignment_id=? WHERE id=?',
            (assignment_id, segment_id)
        )
    return jsonify({'ok': True})


@timeline_bp.route('/api/timeline/strip/segment/unassign', methods=['POST'])
@login_required
def strip_segment_unassign():
    data = request.json or {}
    segment_id = data.get('segment_id')
    if not segment_id:
        return jsonify({'error': 'segment_id required'}), 400
    with db_connect() as conn:
        conn.execute(
            'UPDATE timeline_segments SET assignment_id=NULL WHERE id=?',
            (segment_id,)
        )
    return jsonify({'ok': True})
