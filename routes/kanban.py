import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request

from db import db_connect
from routes.auth import login_required

kanban_bp = Blueprint('kanban', __name__)

DEFAULT_COLUMNS = ['To Do', 'In Progress', 'Done']


def _seed_default_columns(conn):
    """Give a brand-new (or fully emptied) board the standard three columns."""
    if conn.execute('SELECT 1 FROM kanban_columns LIMIT 1').fetchone():
        return
    now = datetime.now().isoformat()
    for pos, title in enumerate(DEFAULT_COLUMNS):
        conn.execute(
            'INSERT INTO kanban_columns (id, title, position, created_at) VALUES (?, ?, ?, ?)',
            (str(uuid.uuid4()), title, pos, now)
        )


def _board(conn):
    cols = conn.execute(
        'SELECT id, title, position FROM kanban_columns ORDER BY position ASC, created_at ASC'
    ).fetchall()
    cards = conn.execute(
        'SELECT id, column_id, title, description, color, position FROM kanban_cards '
        'ORDER BY position ASC, created_at ASC'
    ).fetchall()
    by_col = {}
    for card in cards:
        by_col.setdefault(card['column_id'], []).append(dict(card))
    return [{**dict(col), 'cards': by_col.get(col['id'], [])} for col in cols]


@kanban_bp.route('/api/kanban')
@login_required
def get_board():
    with db_connect() as conn:
        _seed_default_columns(conn)
        return jsonify({'columns': _board(conn)})


# --- columns ---

@kanban_bp.route('/api/kanban/columns', methods=['POST'])
@login_required
def create_column():
    title = _clean((request.json or {}).get('title'))
    if not title:
        return jsonify({'error': 'title required'}), 400
    col_id = str(uuid.uuid4())
    with db_connect() as conn:
        nxt = conn.execute(
            'SELECT COALESCE(MAX(position), -1) + 1 AS p FROM kanban_columns'
        ).fetchone()['p']
        conn.execute(
            'INSERT INTO kanban_columns (id, title, position, created_at) VALUES (?, ?, ?, ?)',
            (col_id, title, nxt, datetime.now().isoformat())
        )
        row = conn.execute(
            'SELECT id, title, position FROM kanban_columns WHERE id=?', (col_id,)
        ).fetchone()
    return jsonify({**dict(row), 'cards': []})


@kanban_bp.route('/api/kanban/columns/<col_id>', methods=['PUT'])
@login_required
def update_column(col_id):
    title = _clean((request.json or {}).get('title'))
    if not title:
        return jsonify({'error': 'title required'}), 400
    with db_connect() as conn:
        cur = conn.execute('UPDATE kanban_columns SET title=? WHERE id=?', (title, col_id))
        if cur.rowcount == 0:
            return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True})


@kanban_bp.route('/api/kanban/columns/<col_id>', methods=['DELETE'])
@login_required
def delete_column(col_id):
    with db_connect() as conn:
        cur = conn.execute('DELETE FROM kanban_columns WHERE id=?', (col_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'not found'}), 404
        conn.execute('DELETE FROM kanban_cards WHERE column_id=?', (col_id,))
    return jsonify({'ok': True})


# --- cards ---

def _clean(value):
    """Coerce any JSON scalar to a stripped string (numbers arrive un-stripped)."""
    return str(value).strip() if value is not None else ''


def _normalize_card(data):
    title = _clean(data.get('title'))
    if not title:
        return None, 'title required'
    return {
        'title': title,
        'description': _clean(data.get('description')) or None,
        'color': _clean(data.get('color')) or None,
    }, None


@kanban_bp.route('/api/kanban/cards', methods=['POST'])
@login_required
def create_card():
    data = request.json or {}
    column_id = _clean(data.get('column_id'))
    card, err = _normalize_card(data)
    if err:
        return jsonify({'error': err}), 400
    if not column_id:
        return jsonify({'error': 'column_id required'}), 400
    card_id = str(uuid.uuid4())
    with db_connect() as conn:
        if not conn.execute('SELECT 1 FROM kanban_columns WHERE id=?', (column_id,)).fetchone():
            return jsonify({'error': 'column not found'}), 404
        nxt = conn.execute(
            'SELECT COALESCE(MAX(position), -1) + 1 AS p FROM kanban_cards WHERE column_id=?',
            (column_id,)
        ).fetchone()['p']
        conn.execute(
            'INSERT INTO kanban_cards (id, column_id, title, description, color, position, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (card_id, column_id, card['title'], card['description'], card['color'],
             nxt, datetime.now().isoformat())
        )
        row = conn.execute(
            'SELECT id, column_id, title, description, color, position FROM kanban_cards WHERE id=?',
            (card_id,)
        ).fetchone()
    return jsonify(dict(row))


@kanban_bp.route('/api/kanban/cards/<card_id>', methods=['PUT'])
@login_required
def update_card(card_id):
    card, err = _normalize_card(request.json or {})
    if err:
        return jsonify({'error': err}), 400
    with db_connect() as conn:
        cur = conn.execute(
            'UPDATE kanban_cards SET title=?, description=?, color=? WHERE id=?',
            (card['title'], card['description'], card['color'], card_id)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'not found'}), 404
        row = conn.execute(
            'SELECT id, column_id, title, description, color, position FROM kanban_cards WHERE id=?',
            (card_id,)
        ).fetchone()
    return jsonify(dict(row))


@kanban_bp.route('/api/kanban/cards/<card_id>', methods=['DELETE'])
@login_required
def delete_card(card_id):
    with db_connect() as conn:
        cur = conn.execute('DELETE FROM kanban_cards WHERE id=?', (card_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True})


@kanban_bp.route('/api/kanban/cards/<card_id>/move', methods=['POST'])
@login_required
def move_card(card_id):
    data = request.json or {}
    target_col = _clean(data.get('column_id'))
    try:
        target_pos = int(data.get('position'))
    except (TypeError, ValueError):
        target_pos = None
    if not target_col or target_pos is None or target_pos < 0:
        return jsonify({'error': 'column_id and position required'}), 400
    with db_connect() as conn:
        card = conn.execute('SELECT column_id FROM kanban_cards WHERE id=?', (card_id,)).fetchone()
        if not card:
            return jsonify({'error': 'not found'}), 404
        if not conn.execute('SELECT 1 FROM kanban_columns WHERE id=?', (target_col,)).fetchone():
            return jsonify({'error': 'column not found'}), 404
        src_col = card['column_id']
        # Rebuild the target column's order with the card inserted at target_pos,
        # then renumber densely; do the same for the source column if it changed.
        others = [r['id'] for r in conn.execute(
            'SELECT id FROM kanban_cards WHERE column_id=? AND id!=? ORDER BY position ASC, created_at ASC',
            (target_col, card_id)
        ).fetchall()]
        target_pos = min(target_pos, len(others))
        others.insert(target_pos, card_id)
        for pos, cid in enumerate(others):
            conn.execute(
                'UPDATE kanban_cards SET column_id=?, position=? WHERE id=?', (target_col, pos, cid)
            )
        if src_col != target_col:
            src_ids = [r['id'] for r in conn.execute(
                'SELECT id FROM kanban_cards WHERE column_id=? ORDER BY position ASC, created_at ASC',
                (src_col,)
            ).fetchall()]
            for pos, cid in enumerate(src_ids):
                conn.execute('UPDATE kanban_cards SET position=? WHERE id=?', (pos, cid))
    return jsonify({'ok': True})
