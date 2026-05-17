from datetime import date

from flask import Blueprint, render_template, session

from db import db_connect
from recurrence import ensure_range_materialized, needs_daily_check, valid_range
from routes.auth import current_user

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def home():
    user = current_user()
    if not user or user['status'] != 'active':
        session.clear()
        return render_template('login.html')

    today = date.today()
    with db_connect() as conn:
        if needs_daily_check(conn, today):
            ensure_range_materialized(conn, today)

    range_start, range_end = valid_range(today)

    return render_template(
        'index.html',
        today_iso=today.isoformat(),
        range_start_iso=range_start.isoformat(),
        range_end_iso=range_end.isoformat(),
        role=user['role'],
        username=user['username'],
    )
