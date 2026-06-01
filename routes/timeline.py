import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request

from db import db_connect
from routes.auth import login_required

timeline_bp = Blueprint('timeline', __name__)


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
        conn.execute(
            'UPDATE timeline_sessions SET stopped_at=? WHERE id=? AND stopped_at IS NULL',
            (now_iso, session_id)
        )
        session = conn.execute('SELECT * FROM timeline_sessions WHERE id=?', (session_id,)).fetchone()
    return jsonify({'session': dict(session) if session else None})


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
        # Enforce the strict-ordering invariant on the server too: the new time
        # must lie between the prev and next anchor points (start, neighbouring
        # marks, or stopped_at / now).
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
        if not (prev_ts < new_ts < next_ts):
            return jsonify({'error': 'marked_at outside neighbour bounds'}), 400
        conn.execute(
            'UPDATE timeline_marks SET marked_at=? WHERE id=?',
            (marked_at, mark_id)
        )
    return jsonify({'ok': True})


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
