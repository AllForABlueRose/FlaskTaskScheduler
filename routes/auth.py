import secrets
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from db import DB

auth_bp = Blueprint('auth', __name__)


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def current_user():
    if 'user_id' not in session:
        return None
    conn = _conn()
    row = conn.execute(
        'SELECT id, username, role, status, session_token FROM users WHERE id=?',
        (session['user_id'],)
    ).fetchone()
    conn.close()
    if not row:
        return None
    if row['role'] == 'admin':
        if not row['session_token'] or session.get('session_token') != row['session_token']:
            return None
    return row


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user['status'] != 'active':
            session.clear()
            return jsonify({'error': 'auth required'}), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user['role'] != 'admin' or user['status'] != 'active':
            session.clear()
            return jsonify({'error': 'admin only'}), 403
        return fn(*args, **kwargs)
    return wrapper


def _set_session(user):
    session.permanent = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    session['status'] = user['status']


@auth_bp.route('/auth/login', methods=['POST'])
def user_login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    conn = _conn()
    user = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'invalid credentials'}), 401
    if user['role'] != 'user':
        return jsonify({'error': 'invalid credentials'}), 401
    if user['status'] != 'active':
        return jsonify({'error': 'account pending approval'}), 403

    _set_session(user)
    return jsonify({'ok': True})


@auth_bp.route('/auth/admin/login', methods=['POST'])
def admin_login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    conn = _conn()
    user = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()

    if not user or not check_password_hash(user['password_hash'], password):
        conn.close()
        return jsonify({'error': 'invalid credentials'}), 401
    if user['role'] != 'admin':
        conn.close()
        return jsonify({'error': 'invalid credentials'}), 401

    token = secrets.token_hex(16)
    conn.execute('UPDATE users SET session_token=? WHERE id=?', (token, user['id']))
    conn.commit()
    conn.close()

    _set_session(user)
    session['session_token'] = token
    return jsonify({'ok': True})


@auth_bp.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})


@auth_bp.route('/auth/signup', methods=['POST'])
def signup():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    confirm = data.get('confirm') or ''

    if not username or not password:
        return jsonify({'error': 'username and password required'}), 400
    if password != confirm:
        return jsonify({'error': 'passwords do not match'}), 400

    conn = _conn()
    existing = conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'username already taken'}), 409

    conn.execute(
        'INSERT INTO users (username, password_hash, role, status, created_at) VALUES (?, ?, ?, ?, ?)',
        (username, generate_password_hash(password), 'user', 'pending', datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@auth_bp.route('/admin/users')
@admin_required
def list_users():
    conn = _conn()
    rows = conn.execute(
        'SELECT id, username, role, status, created_at FROM users ORDER BY status, created_at'
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@auth_bp.route('/admin/users/<int:user_id>/approve', methods=['POST'])
@admin_required
def approve_user(user_id):
    conn = _conn()
    conn.execute(
        "UPDATE users SET status='active' WHERE id=? AND status='pending' AND role='user'",
        (user_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@auth_bp.route('/admin/users/<int:user_id>/reject', methods=['POST'])
@admin_required
def reject_user(user_id):
    conn = _conn()
    conn.execute(
        "DELETE FROM users WHERE id=? AND status='pending' AND role='user'",
        (user_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@auth_bp.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_password(user_id):
    data = request.json or {}
    new_password = data.get('password') or ''
    if not new_password:
        return jsonify({'error': 'password required'}), 400

    conn = _conn()
    conn.execute(
        'UPDATE users SET password_hash=? WHERE id=?',
        (generate_password_hash(new_password), user_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@auth_bp.route('/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def revoke_user(user_id):
    conn = _conn()
    user = conn.execute('SELECT role FROM users WHERE id=?', (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'not found'}), 404
    if user['role'] == 'admin':
        conn.close()
        return jsonify({'error': 'cannot revoke admin'}), 403
    conn.execute('DELETE FROM users WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})
