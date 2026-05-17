import json
import uuid
from datetime import date

from flask import Blueprint, jsonify, request

from db import db_connect
from recurrence import (
    detach_recurring_entries,
    materialize_task,
    parse_recurrence,
    valid_range,
)
from routes.auth import login_required

tasks_bp = Blueprint('tasks', __name__)


@tasks_bp.route('/tasks')
@login_required
def get_tasks():
    with db_connect() as conn:
        rows = conn.execute('SELECT * FROM tasks').fetchall()
    return jsonify([dict(r) for r in rows])


@tasks_bp.route('/task', methods=['POST'])
@login_required
def create_task():
    data = request.json

    task = {
        'id': str(uuid.uuid4()),
        'input': '',
        **data
    }

    with db_connect() as conn:
        conn.execute(
            'INSERT INTO tasks (id, name, description, tags, color, code, input) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                task['id'],
                task['name'],
                task['description'],
                task['tags'],
                task['color'],
                task['code'],
                task['input'],
            )
        )

    return jsonify(task)


@tasks_bp.route('/task/<task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    data = request.json

    with db_connect() as conn:
        conn.execute(
            'UPDATE tasks SET name=?, description=?, tags=?, color=?, code=?, input=? WHERE id=?',
            (
                data['name'],
                data['description'],
                data['tags'],
                data['color'],
                data['code'],
                data.get('input', ''),
                task_id,
            )
        )

    return jsonify({'id': task_id, **data})


@tasks_bp.route('/task/<task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    with db_connect() as conn:
        conn.execute('DELETE FROM tasks WHERE id=?', (task_id,))
        conn.execute('DELETE FROM schedule WHERE task_id=?', (task_id,))
    return jsonify({'ok': True})


@tasks_bp.route('/task/<task_id>/recurrence', methods=['POST'])
@login_required
def set_recurrence(task_id):
    data = request.json or {}
    recurrence = parse_recurrence(data.get('recurrence'))
    rec_json = json.dumps(recurrence) if recurrence else None

    with db_connect() as conn:
        existing = conn.execute('SELECT id FROM tasks WHERE id=?', (task_id,)).fetchone()
        if existing is None:
            return jsonify({'error': 'task not found'}), 404

        conn.execute(
            'UPDATE tasks SET recurrence=?, tags=?, description=? WHERE id=?',
            (
                rec_json,
                data.get('tags', ''),
                data.get('description', ''),
                task_id,
            )
        )

        today = date.today()
        range_start, range_end = valid_range(today)
        if recurrence:
            materialize_task(conn, task_id, recurrence, range_start, range_end)
        else:
            detach_recurring_entries(conn, task_id)

        row = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()

    return jsonify(dict(row))
