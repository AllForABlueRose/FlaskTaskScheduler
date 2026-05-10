import sqlite3

from flask import Blueprint, jsonify, request

from db import DB
from routes.auth import login_required

schedule_bp = Blueprint('schedule', __name__)


@schedule_bp.route('/schedule')
@login_required
def get_schedule():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT id, slot, task_id, duration FROM schedule'
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@schedule_bp.route('/schedule', methods=['POST'])
@login_required
def schedule_task():
    data = request.json

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    task = conn.execute(
        'SELECT * FROM tasks WHERE id=?',
        (data['taskId'],)
    ).fetchone()

    if task is None:
        conn.close()
        return jsonify({'error': 'task not found'}), 404

    duration = max(1, int(data.get('duration') or 1))
    entry_id = data.get('id')
    slot = data['slot']

    if entry_id:
        conn.execute(
            'UPDATE schedule SET slot=?, duration=?, task_id=?, last_run_at=NULL WHERE id=?',
            (slot, duration, task['id'], entry_id)
        )
    else:
        cur = conn.execute(
            'INSERT INTO schedule (slot, task_id, duration) VALUES (?, ?, ?)',
            (slot, task['id'], duration)
        )
        entry_id = cur.lastrowid

    conn.commit()
    conn.close()

    return jsonify({
        'id': entry_id,
        'slot': slot,
        'task_id': task['id'],
        'duration': duration,
    })


@schedule_bp.route('/schedule/remove', methods=['POST'])
@login_required
def remove_scheduled():
    data = request.json
    conn = sqlite3.connect(DB)
    conn.execute('DELETE FROM schedule WHERE id=?', (data['id'],))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})
