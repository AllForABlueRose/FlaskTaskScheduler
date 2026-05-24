"""Round-trip smoke tests for the HTTP API.

Uses Flask's test_client against a fresh tempfile DB per test. Catches the
class of bugs that ad-hoc smoke tests caught during development (e.g., the
`/schedule` page vs `/api/schedule` JSON collision, blueprint registration
gaps, validation regressions) so they fail at `python3 -m unittest` time
instead of in the browser.

stdlib-only: no test deps. Mirrors the tempfile-DB pattern from
`tests/test_recurrence._DbTestBase`.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import db as db_module
from werkzeug.security import generate_password_hash


class RouteTestBase(unittest.TestCase):
    """Each test starts on a fresh tempfile DB with one active user logged in."""

    USERNAME = 'alice'
    PASSWORD = 'pw'

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.tmp.close()
        self._orig_db = db_module.DB
        db_module.DB = self.tmp.name
        db_module.init_db()

        with db_module.db_connect() as conn:
            conn.execute(
                'INSERT INTO users (username, password_hash, role, status, created_at) '
                'VALUES (?, ?, ?, ?, ?)',
                (self.USERNAME, generate_password_hash(self.PASSWORD), 'user',
                 'active', datetime.now().isoformat())
            )

        from app import create_app
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        r = self.client.post('/auth/login',
                             json={'username': self.USERNAME, 'password': self.PASSWORD})
        self.assertEqual(r.status_code, 200, f'login failed: {r.data!r}')

    def tearDown(self):
        db_module.DB = self._orig_db
        os.unlink(self.tmp.name)


class PageRouteTests(RouteTestBase):
    def test_root_redirects_to_schedule(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/schedule', r.headers.get('Location', ''))

    def test_schedule_page_serves_html(self):
        r = self.client.get('/schedule')
        self.assertEqual(r.status_code, 200)
        self.assertIn('text/html', r.content_type)
        body = r.get_data(as_text=True)
        self.assertIn('data-initial-tab="schedule"', body)
        self.assertIn('id="view-schedule"', body)
        self.assertIn('id="view-events"', body)

    def test_events_page_serves_html(self):
        r = self.client.get('/events')
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn('data-initial-tab="events"', body)
        self.assertIn('id="eventsGrid"', body)
        self.assertIn('id="eventsSidebar"', body)
        self.assertIn('id="eventModal"', body)


class AuthTests(RouteTestBase):
    def test_protected_endpoint_returns_401_after_logout(self):
        self.assertEqual(self.client.get('/tasks').status_code, 200)
        self.client.post('/auth/logout')
        r = self.client.get('/tasks')
        self.assertEqual(r.status_code, 401)

    def test_wrong_password_rejected(self):
        c = self.app.test_client()
        r = c.post('/auth/login',
                   json={'username': self.USERNAME, 'password': 'WRONG'})
        self.assertEqual(r.status_code, 401)

    def test_unauthenticated_api_returns_401(self):
        c = self.app.test_client()
        for path in ('/tasks', '/api/schedule', '/api/events',
                     '/api/event-categories', '/logs'):
            r = c.get(path)
            self.assertEqual(r.status_code, 401,
                             f'{path} returned {r.status_code}, want 401')


class TasksApiTests(RouteTestBase):
    def test_task_crud_roundtrip(self):
        self.assertEqual(self.client.get('/tasks').get_json(), [])

        payload = {'name': 'T1', 'description': 'd', 'tags': 'a,b',
                   'color': '#3b82f6', 'code': 'print("x")'}
        r = self.client.post('/task', json=payload)
        self.assertEqual(r.status_code, 200, r.data)
        task = r.get_json()
        self.assertEqual(task['name'], 'T1')
        task_id = task['id']

        listing = self.client.get('/tasks').get_json()
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]['id'], task_id)

        r = self.client.put(f'/task/{task_id}',
                            json={**payload, 'name': 'T1-renamed'})
        self.assertEqual(r.status_code, 200, r.data)

        r = self.client.delete(f'/task/{task_id}')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.client.get('/tasks').get_json(), [])


class ScheduleApiTests(RouteTestBase):
    """Regression coverage for the /schedule page vs /api/schedule JSON split."""

    def test_schedule_path_serves_html_not_json(self):
        r = self.client.get('/schedule')
        self.assertIn('text/html', r.content_type)
        self.assertNotIn('application/json', r.content_type)

    def test_api_schedule_returns_json_list(self):
        r = self.client.get('/api/schedule')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [])

    def test_schedule_entry_lifecycle(self):
        task = self.client.post('/task', json={
            'name': 'T', 'description': '', 'tags': '',
            'color': '#3b82f6', 'code': '',
        }).get_json()

        r = self.client.post('/api/schedule', json={
            'taskId': task['id'], 'slot': '2026-05-25-9-0', 'duration': 2,
        })
        self.assertEqual(r.status_code, 200, r.data)
        entry = r.get_json()
        self.assertEqual(entry['slot'], '2026-05-25-9-0')

        items = self.client.get('/api/schedule').get_json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['task_id'], task['id'])

        r = self.client.post(f'/api/schedule/{entry["id"]}/input',
                             json={'input': 'val1'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['input'], 'val1')

        r = self.client.post('/api/schedule/remove', json={'id': entry['id']})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get('/api/schedule').get_json(), [])


class EventsApiTests(RouteTestBase):
    def test_event_crud_roundtrip(self):
        self.assertEqual(self.client.get('/api/events').get_json(), [])

        r = self.client.post('/api/events', json={
            'title': 'Conf', 'start_date': '2026-05-25',
            'end_date': '2026-05-27', 'category': 'Work',
            'color': '#3b82f6', 'description': 'desc',
        })
        self.assertEqual(r.status_code, 200, r.data)
        ev = r.get_json()
        self.assertEqual(ev['title'], 'Conf')

        listing = self.client.get('/api/events').get_json()
        self.assertEqual(len(listing), 1)

        r = self.client.put(f'/api/events/{ev["id"]}', json={
            **ev, 'title': 'Conf-renamed',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['title'], 'Conf-renamed')

        r = self.client.delete(f'/api/events/{ev["id"]}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get('/api/events').get_json(), [])

    def test_range_filter_includes_overlapping_and_excludes_non(self):
        self.client.post('/api/events', json={
            'title': 'X', 'start_date': '2026-05-25',
            'end_date': '2026-05-27', 'category': '', 'color': '',
            'description': '',
        })
        overlap = self.client.get(
            '/api/events?range_start=2026-05-01&range_end=2026-05-31'
        ).get_json()
        self.assertEqual(len(overlap), 1)
        miss = self.client.get(
            '/api/events?range_start=2026-07-01&range_end=2026-07-31'
        ).get_json()
        self.assertEqual(len(miss), 0)

    def test_categories_endpoint_surfaces_most_recent_color(self):
        self.client.post('/api/events', json={
            'title': 'A', 'start_date': '2026-05-01', 'end_date': '2026-05-01',
            'category': 'Work', 'color': '#3b82f6', 'description': '',
        })
        self.client.post('/api/events', json={
            'title': 'B', 'start_date': '2026-05-02', 'end_date': '2026-05-02',
            'category': 'Work', 'color': '#10b981', 'description': '',
        })
        cats = self.client.get('/api/event-categories').get_json()
        work = [c for c in cats if c['name'] == 'Work']
        self.assertEqual(len(work), 1, f'expected one Work entry, got {cats}')
        self.assertEqual(work[0]['color'], '#10b981',
                         'categories endpoint should surface most-recently-used color')

    def test_validation_rejects_missing_title(self):
        r = self.client.post('/api/events', json={
            'title': '', 'start_date': '2026-05-25', 'end_date': '2026-05-25',
        })
        self.assertEqual(r.status_code, 400)

    def test_validation_rejects_missing_dates(self):
        r = self.client.post('/api/events', json={
            'title': 'X', 'start_date': '', 'end_date': '2026-05-25',
        })
        self.assertEqual(r.status_code, 400)

    def test_validation_rejects_inverted_dates(self):
        r = self.client.post('/api/events', json={
            'title': 'X', 'start_date': '2026-05-25', 'end_date': '2026-05-20',
        })
        self.assertEqual(r.status_code, 400)

    def test_404_on_missing_event_id(self):
        r = self.client.put('/api/events/no-such-id', json={
            'title': 'X', 'start_date': '2026-05-25', 'end_date': '2026-05-25',
        })
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.client.delete('/api/events/no-such-id').status_code, 404)


class LogsApiTests(RouteTestBase):
    def test_logs_returns_cursor_and_entries(self):
        r = self.client.get('/logs?since=0')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn('cursor', data)
        self.assertIn('entries', data)
        self.assertIsInstance(data['entries'], list)


if __name__ == '__main__':
    unittest.main()
