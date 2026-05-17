from flask import Blueprint, jsonify, request

from request_log import get_entries_since
from routes.auth import login_required

logs_bp = Blueprint('logs', __name__)


@logs_bp.route('/logs')
@login_required
def get_logs():
    try:
        cursor = int(request.args.get('since', 0))
    except ValueError:
        cursor = 0
    entries = get_entries_since(cursor)
    next_cursor = entries[-1]['id'] if entries else cursor
    return jsonify({'entries': entries, 'cursor': next_cursor})
