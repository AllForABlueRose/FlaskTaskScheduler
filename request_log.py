import logging
import time
from collections import deque
from threading import Lock

from flask import request, session

_BUF_MAXLEN = 500
_buffer = deque(maxlen=_BUF_MAXLEN)
_lock = Lock()
_seq = 0


def init_logging():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)


def _should_log(req, resp):
    path = req.path
    method = req.method
    if path.startswith('/static/'):
        return False
    if path == '/favicon.ico':
        return False
    if path.startswith('/logs'):
        return False
    if method == 'GET' and path in ('/tasks', '/api/schedule', '/api/events', '/api/event-categories', '/admin/users', '/api/applications/files'):
        return False
    return True


def _record(req, resp):
    global _seq
    user = session.get('username') or '-'
    entry_time = time.strftime('%H:%M:%S')
    with _lock:
        _seq += 1
        entry = {
            'id': _seq,
            'time': entry_time,
            'method': req.method,
            'path': req.path,
            'status': resp.status_code,
            'user': user,
        }
        _buffer.append(entry)
    print(
        f'[{entry_time}] {user} {req.method} {req.path} -> {resp.status_code}',
        flush=True,
    )


def get_entries_since(cursor):
    with _lock:
        return [e for e in _buffer if e['id'] > cursor]


def register(app):
    @app.after_request
    def _after(resp):
        if _should_log(request, resp):
            _record(request, resp)
        return resp
    return app
