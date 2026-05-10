import sqlite3
import uuid

from flask import Blueprint, jsonify, request

from db import DB
from routes.auth import login_required

tasks_bp = Blueprint('tasks', __name__)


@tasks_bp.route('/tasks')
@login_required
def get_tasks():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT * FROM tasks').fetchall()
    conn.close()
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

    conn = sqlite3.connect(DB)
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
    conn.commit()
    conn.close()

    return jsonify(task)


@tasks_bp.route('/task/<task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    data = request.json

    conn = sqlite3.connect(DB)
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
    conn.commit()
    conn.close()

    return jsonify({'id': task_id, **data})


@tasks_bp.route('/task/<task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    conn = sqlite3.connect(DB)
    conn.execute('DELETE FROM tasks WHERE id=?', (task_id,))
    conn.execute('DELETE FROM schedule WHERE task_id=?', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})
