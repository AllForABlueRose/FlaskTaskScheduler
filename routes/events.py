import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request

from db import db_connect
from routes.auth import login_required

events_bp = Blueprint('events', __name__)


def _normalize(data):
    title = (data.get('title') or '').strip()
    start = (data.get('start_date') or '').strip()
    end = (data.get('end_date') or '').strip()
    if not title or not start or not end:
        return None, 'title, start_date, end_date are required'
    if end < start:
        return None, 'end_date must be on or after start_date'
    return {
        'title': title,
        'start_date': start,
        'end_date': end,
        'category': (data.get('category') or '').strip() or None,
        'color': (data.get('color') or '').strip() or None,
        'description': (data.get('description') or '').strip() or None,
    }, None


@events_bp.route('/api/events')
@login_required
def list_events():
    range_start = request.args.get('range_start')
    range_end = request.args.get('range_end')
    with db_connect() as conn:
        if range_start and range_end:
            rows = conn.execute(
                'SELECT * FROM events WHERE end_date >= ? AND start_date <= ? '
                'ORDER BY start_date ASC, end_date ASC, title ASC',
                (range_start, range_end)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM events ORDER BY start_date ASC, end_date ASC, title ASC'
            ).fetchall()
    return jsonify([dict(r) for r in rows])


@events_bp.route('/api/events', methods=['POST'])
@login_required
def create_event():
    data, err = _normalize(request.json or {})
    if err:
        return jsonify({'error': err}), 400
    event_id = str(uuid.uuid4())
    with db_connect() as conn:
        conn.execute(
            'INSERT INTO events (id, title, start_date, end_date, category, color, description, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (event_id, data['title'], data['start_date'], data['end_date'],
             data['category'], data['color'], data['description'], datetime.now().isoformat())
        )
        row = conn.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
    return jsonify(dict(row))


@events_bp.route('/api/events/<event_id>', methods=['PUT'])
@login_required
def update_event(event_id):
    data, err = _normalize(request.json or {})
    if err:
        return jsonify({'error': err}), 400
    with db_connect() as conn:
        cur = conn.execute(
            'UPDATE events SET title=?, start_date=?, end_date=?, category=?, color=?, description=? WHERE id=?',
            (data['title'], data['start_date'], data['end_date'],
             data['category'], data['color'], data['description'], event_id)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'not found'}), 404
        row = conn.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
    return jsonify(dict(row))


@events_bp.route('/api/events/<event_id>', methods=['DELETE'])
@login_required
def delete_event(event_id):
    with db_connect() as conn:
        cur = conn.execute('DELETE FROM events WHERE id=?', (event_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True})


@events_bp.route('/api/event-categories')
@login_required
def list_categories():
    """Return distinct categories with the most-recently-used color for each."""
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT category, color FROM events "
            "WHERE category IS NOT NULL AND category != '' "
            "ORDER BY created_at DESC"
        ).fetchall()
    seen = {}
    for r in rows:
        name = r['category']
        if name not in seen:
            seen[name] = r['color']
    return jsonify([{'name': k, 'color': v} for k, v in seen.items()])
