import os
import threading
from datetime import timedelta

from flask import Flask

import request_log
from db import init_db
from keep_awake import prevent_sleep
from ledger import init_ledger_db
from routes.auth import auth_bp
from routes.applications import applications_bp
from routes.events import events_bp
from routes.kanban import kanban_bp
from routes.logs import logs_bp
from routes.main import main_bp
from routes.schedule import schedule_bp
from routes.tasks import tasks_bp
from routes.timeline import timeline_bp
from scheduler import run_scheduler


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-change-me')
    app.permanent_session_lifetime = timedelta(days=1)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(timeline_bp)
    app.register_blueprint(kanban_bp)
    app.register_blueprint(logs_bp)
    request_log.register(app)
    return app


if __name__ == '__main__':
    request_log.init_logging()
    init_db()
    init_ledger_db()
    prevent_sleep()
    threading.Thread(target=run_scheduler, daemon=True).start()
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
