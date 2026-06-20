from datetime import date

from flask import Blueprint, redirect, render_template, session, url_for

from db import db_connect
from recurrence import ensure_range_materialized, needs_daily_check, valid_range
from routes.auth import current_user

main_bp = Blueprint('main', __name__)


def _render_app(initial_tab):
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
        initial_tab=initial_tab,
    )


@main_bp.route('/')
def home():
    return redirect(url_for('main.schedule_view'))


@main_bp.route('/schedule')
def schedule_view():
    return _render_app('schedule')


@main_bp.route('/events')
def events_view():
    return _render_app('events')


@main_bp.route('/applications')
def applications_view():
    return _render_app('applications')


@main_bp.route('/timeline')
def timeline_view():
    return _render_app('timeline')
  
  
@main_bp.route('/taskboard')
def taskboard_view():
    return _render_app('taskboard')
