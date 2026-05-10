from datetime import datetime, timedelta

from flask import Blueprint, render_template, session

from routes.auth import current_user

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def home():
    user = current_user()
    if not user or user['status'] != 'active':
        session.clear()
        return render_template('login.html')

    today = datetime.now()
    start = today - timedelta(days=today.weekday())

    days = [
        (start + timedelta(days=i)).strftime('%a %m/%d')
        for i in range(7)
    ]

    today_str = today.strftime('%a %m/%d')

    return render_template(
        'index.html',
        days=days,
        today_str=today_str,
        role=user['role'],
        username=user['username'],
    )
