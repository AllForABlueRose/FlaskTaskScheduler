from flask import Blueprint, jsonify, request

from db import db_connect
from routes.auth import login_required

schedule_bp = Blueprint('schedule', __name__)


@schedule_bp.route('/schedule')
@login_required
def get_schedule():
    with db_connect() as conn:
        rows = conn.execute(
            'SELECT id, slot, task_id, duration, is_recurring, input FROM schedule'
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@schedule_bp.route('/schedule', methods=['POST'])
@login_required
def schedule_task():
    data = request.json

    with db_connect() as conn:
        task = conn.execute(
            'SELECT * FROM tasks WHERE id=?',
            (data['taskId'],)
        ).fetchone()

        if task is None:
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
    with db_connect() as conn:
        conn.execute('DELETE FROM schedule WHERE id=?', (data['id'],))
    return jsonify({'ok': True})


@schedule_bp.route('/schedule/<int:entry_id>/input', methods=['POST'])
@login_required
def set_entry_input(entry_id):
    data = request.json or {}
    if 'input' not in data:
        return jsonify({'error': 'input field required'}), 400
    val = data['input']
    stored = None if val is None else str(val)
    with db_connect() as conn:
        cur = conn.execute(
            'UPDATE schedule SET input=? WHERE id=?',
            (stored, entry_id)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'not found'}), 404
    return jsonify({'id': entry_id, 'input': stored})
