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
import ledger as ledger_module
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

        self.tmp_approvals = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.tmp_approvals.close()
        self._orig_approvals_db = ledger_module.APPROVALS_DB
        ledger_module.APPROVALS_DB = self.tmp_approvals.name
        ledger_module.init_ledger_db()

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
        ledger_module.APPROVALS_DB = self._orig_approvals_db
        os.unlink(self.tmp_approvals.name)


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


class ApplicationsChangeDetectionTests(RouteTestBase):
    """Change detection is mtime-based and must behave identically for every
    supported file type — the listing endpoint never parses file contents."""

    # one file per supported type; contents are irrelevant to detection
    TYPED_FILES = {
        'sheet.xlsx': 'excel',
        'memo.docx': 'word',
        'scan.pdf': 'pdf',
        'photo.png': 'image',
    }

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        for name in self.TYPED_FILES:
            self._write(name, b'original')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.folder, ignore_errors=True)
        super().tearDown()

    def _write(self, name, content):
        with open(os.path.join(self.folder, name), 'wb') as f:
            f.write(content)

    def _touch(self, name, offset_seconds=120):
        """Bump mtime deterministically without sleeping."""
        path = os.path.join(self.folder, name)
        st = os.stat(path)
        os.utime(path, (st.st_atime, st.st_mtime + offset_seconds))

    def _list(self):
        r = self.client.get('/api/applications/files?folder=' + self.folder)
        self.assertEqual(r.status_code, 200)
        return {f['name']: f for f in r.get_json()['files']}

    def _set_status(self, name, status):
        r = self.client.post('/api/applications/file/status', json={
            'folder': self.folder, 'filename': name, 'status': status,
        })
        self.assertEqual(r.status_code, 200)

    def test_all_types_listed_without_status(self):
        files = self._list()
        for name, ftype in self.TYPED_FILES.items():
            self.assertIn(name, files)
            self.assertEqual(files[name]['type'], ftype)
            self.assertNotIn('status', files[name])

    def test_approved_unchanged_stays_approved_all_types(self):
        for name in self.TYPED_FILES:
            self._set_status(name, 'approved')
        files = self._list()
        for name in self.TYPED_FILES:
            self.assertEqual(files[name].get('status'), 'approved', name)

    def test_approved_then_changed_reports_modified_all_types(self):
        for name in self.TYPED_FILES:
            self._set_status(name, 'approved')
            self._write(name, b'changed content')
            self._touch(name)
        files = self._list()
        for name in self.TYPED_FILES:
            self.assertEqual(files[name].get('status'), 'modified', name)

    def test_reapproval_after_change_restores_approved(self):
        name = 'sheet.xlsx'
        self._set_status(name, 'approved')
        self._write(name, b'v2')
        self._touch(name)
        self.assertEqual(self._list()[name].get('status'), 'modified')
        self._set_status(name, 'approved')
        self.assertEqual(self._list()[name].get('status'), 'approved')

    def test_flag_autoclears_on_change_all_types(self):
        for name in self.TYPED_FILES:
            self._set_status(name, 'flagged')
            self._touch(name)
        files = self._list()
        for name in self.TYPED_FILES:
            self.assertNotIn('status', files[name], name)

    def test_flag_persists_when_unchanged(self):
        name = 'memo.docx'
        self._set_status(name, 'flagged')
        self.assertEqual(self._list()[name].get('status'), 'flagged')

    def test_flag_on_modified_file_wins_over_modified(self):
        name = 'scan.pdf'
        self._set_status(name, 'approved')
        self._write(name, b'v2')
        self._touch(name)
        self._set_status(name, 'flagged')
        self.assertEqual(self._list()[name].get('status'), 'flagged')

    def test_rejected_unchanged_shows_rejected(self):
        name = 'photo.png'
        self._set_status(name, 'rejected')
        self.assertEqual(self._list()[name].get('status'), 'rejected')

    def test_rejected_then_changed_reappears_with_ghost(self):
        name = 'photo.png'
        self._set_status(name, 'rejected')
        self._write(name, b'replacement')
        self._touch(name)
        r = self.client.get('/api/applications/files?folder=' + self.folder)
        entries = [f for f in r.get_json()['files'] if f['name'] == name]
        ghosts = [f for f in entries if f.get('ghost')]
        fresh = [f for f in entries if not f.get('ghost')]
        self.assertEqual(len(ghosts), 1)
        self.assertEqual(len(fresh), 1)
        self.assertNotIn('status', fresh[0])


class ApprovalLedgerTests(RouteTestBase):
    """Hash-chained ledger + blob store behaviors behind the approval flow."""

    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        self.folder = os.path.join(self.root, 'clientA', 'projectB')
        os.makedirs(self.folder)
        self.fname = 'photo.png'
        self.original = b'png-bytes-v1'
        with open(os.path.join(self.folder, self.fname), 'wb') as f:
            f.write(self.original)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)
        super().tearDown()

    def _approve(self, name=None):
        r = self.client.post('/api/applications/file/status', json={
            'folder': self.folder, 'filename': name or self.fname, 'status': 'approved',
        })
        self.assertEqual(r.status_code, 200)

    def _status_of(self, name=None):
        r = self.client.get('/api/applications/files?folder=' + self.folder)
        files = {f['name']: f for f in r.get_json()['files']}
        return files[name or self.fname].get('status')

    def _verify(self):
        r = self.client.get('/api/applications/ledger/verify')
        self.assertEqual(r.status_code, 200)
        return r.get_json()

    def test_approve_appends_verified_entry_and_blob(self):
        import hashlib
        self._approve()
        with ledger_module.ledger_connect() as conn:
            rows = conn.execute('SELECT * FROM approval_ledger').fetchall()
            self.assertEqual(len(rows), 1)
            entry = rows[0]
            self.assertEqual(entry['content_sha256'], hashlib.sha256(self.original).hexdigest())
            self.assertEqual(entry['approved_path'], 'clientA/projectB/' + self.fname)
            self.assertEqual(entry['folder'], self.folder)
            self.assertEqual(entry['approved_by'], self.USERNAME)
            self.assertEqual(ledger_module.fetch_blob(conn, entry['content_sha256']), self.original)
        result = self._verify()
        self.assertTrue(result['ok'], result['errors'])

    def test_mtime_spoofing_does_not_evade_detection(self):
        self._approve()
        path = os.path.join(self.folder, self.fname)
        st = os.stat(path)
        with open(path, 'wb') as f:
            f.write(b'png-bytes-TAMPERED')
        os.utime(path, (st.st_atime, st.st_mtime))  # restore original mtime
        self.assertEqual(self._status_of(), 'modified')

    def test_reapproval_extends_chain(self):
        self._approve()
        with open(os.path.join(self.folder, self.fname), 'wb') as f:
            f.write(b'png-bytes-v2')
        self.assertEqual(self._status_of(), 'modified')
        self._approve()
        self.assertEqual(self._status_of(), 'approved')
        with ledger_module.ledger_connect() as conn:
            count = conn.execute('SELECT COUNT(*) FROM approval_ledger').fetchone()[0]
        self.assertEqual(count, 2)
        result = self._verify()
        self.assertTrue(result['ok'], result['errors'])

    def test_tampered_blob_is_detected(self):
        self._approve()
        with ledger_module.ledger_connect() as conn:
            conn.execute('UPDATE approved_blobs SET content=?', (b'evil-content',))
        result = self._verify()
        self.assertFalse(result['ok'])
        self.assertTrue(any('blob' in e for e in result['errors']))
        r = self.client.get('/api/applications/file/preview?folder=clientA/projectB'
                            + '&name=' + self.fname + '&approved=1')
        self.assertEqual(r.status_code, 409)

    def test_tampered_ledger_row_is_detected(self):
        self._approve()
        with ledger_module.ledger_connect() as conn:
            conn.execute("UPDATE approval_ledger SET approved_by='mallory'")
        result = self._verify()
        self.assertFalse(result['ok'])
        self.assertTrue(any('entry hash mismatch' in e for e in result['errors']))

    def test_approved_preview_serves_ledger_snapshot_not_disk(self):
        self._approve()
        with open(os.path.join(self.folder, self.fname), 'wb') as f:
            f.write(b'png-bytes-CHANGED-ON-DISK')
        r = self.client.get('/api/applications/file/preview?folder=clientA/projectB'
                            + '&name=' + self.fname + '&approved=1')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, self.original)

    def test_approved_tree_built_from_ledger(self):
        self._approve()
        r = self.client.get('/api/applications/approved-tree')
        tree = r.get_json()['tree']
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]['name'], 'clientA')
        self.assertEqual(tree[0]['children'][0]['name'], 'projectB')
        leaf = tree[0]['children'][0]['children'][0]
        self.assertEqual(leaf['name'], self.fname)
        self.assertEqual(leaf['type'], 'image')
        self.assertTrue(leaf['approved_at'])


class MigrationScriptTests(RouteTestBase):
    """scripts/migrate_approved_to_ledger.py against a legacy approved/ layout."""

    def setUp(self):
        super().setUp()
        self.approved_dir = tempfile.mkdtemp()
        deep = os.path.join(self.approved_dir, 'clientA', 'projectB')
        os.makedirs(deep)
        with open(os.path.join(deep, 'sheet.xlsx'), 'wb') as f:
            f.write(b'xlsx-approved-content')
        with open(os.path.join(deep, 'orphan.pdf'), 'wb') as f:
            f.write(b'pdf-orphan-content')

        # legacy record for sheet.xlsx — Windows-style approved_path on purpose
        with db_module.db_connect() as conn:
            conn.execute(
                'INSERT INTO app_file_status (folder, filename, status, file_mtime, created_at, approved_path) '
                "VALUES (?, ?, 'approved', ?, ?, ?)",
                ('/data/source/projectB', 'sheet.xlsx', '2026-01-01T10:00:00',
                 '2026-01-02T09:00:00', 'clientA\\projectB\\sheet.xlsx')
            )
            # record whose copy is missing on disk
            conn.execute(
                'INSERT INTO app_file_status (folder, filename, status, file_mtime, created_at, approved_path) '
                "VALUES (?, ?, 'approved', ?, ?, ?)",
                ('/data/source/projectB', 'gone.docx', '2026-01-01T11:00:00',
                 '2026-01-03T09:00:00', 'clientA/projectB/gone.docx')
            )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.approved_dir, ignore_errors=True)
        super().tearDown()

    def _run(self, *extra):
        import importlib
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
        try:
            script = importlib.import_module('migrate_approved_to_ledger')
        finally:
            sys.path.pop(0)
        return script.main([
            '--approved-dir', self.approved_dir,
            '--scheduler-db', db_module.DB,
            '--approvals-db', ledger_module.APPROVALS_DB,
            *extra,
        ])

    def test_dry_run_writes_nothing(self):
        self.assertEqual(self._run('--dry-run'), 0)
        with ledger_module.ledger_connect() as conn:
            count = conn.execute('SELECT COUNT(*) FROM approval_ledger').fetchone()[0]
        self.assertEqual(count, 0)

    def test_migration_ingests_and_chain_verifies(self):
        import hashlib
        self.assertEqual(self._run(), 0)
        with ledger_module.ledger_connect() as conn:
            rows = {r['approved_path']: r for r in
                    conn.execute('SELECT * FROM approval_ledger').fetchall()}
            result = ledger_module.verify_chain(conn)
        self.assertTrue(result['ok'], result['errors'])
        self.assertEqual(set(rows), {'clientA/projectB/sheet.xlsx', 'clientA/projectB/orphan.pdf'})

        matched = rows['clientA/projectB/sheet.xlsx']
        self.assertEqual(matched['folder'], '/data/source/projectB')
        self.assertEqual(matched['created_at'], '2026-01-02T09:00:00')
        self.assertEqual(matched['content_sha256'],
                         hashlib.sha256(b'xlsx-approved-content').hexdigest())

        orphan = rows['clientA/projectB/orphan.pdf']
        self.assertEqual(orphan['folder'], '')
        self.assertEqual(orphan['approved_by'], 'migration-orphan')

    def test_second_run_refused_without_append(self):
        self.assertEqual(self._run(), 0)
        self.assertEqual(self._run(), 1)

    def test_migrated_file_previews_and_lists(self):
        self.assertEqual(self._run(), 0)
        # pdf/image previews return raw blob bytes (excel/word are parsed server-side)
        r = self.client.get('/api/applications/file/preview?folder=clientA/projectB'
                            + '&name=orphan.pdf&approved=1')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, b'pdf-orphan-content')
        r = self.client.get('/api/applications/approved-tree')
        tree = r.get_json()['tree']
        self.assertEqual(tree[0]['name'], 'clientA')
        names = {c['name'] for c in tree[0]['children'][0]['children']}
        self.assertEqual(names, {'sheet.xlsx', 'orphan.pdf'})


class TracesApiTests(RouteTestBase):
    """Lifecycle coverage for the Traces feature: template -> run -> seal."""

    # a valid 1x1 PNG
    PNG_DATA_URL = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1'
                    'HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')

    def _draft_with_pages(self, n=2, title='WF'):
        wf = self.client.post('/api/traces/workflows', json={'title': title}).get_json()
        for i in range(n):
            r = self.client.post(f'/api/traces/workflows/{wf["id"]}/pages',
                                  json={'title': f'P{i}', 'explanation': f'put image {i}'})
            self.assertEqual(r.status_code, 200, r.data)
        return wf['id']

    def _concluded(self, n=2, title='WF'):
        wf_id = self._draft_with_pages(n, title)
        r = self.client.post(f'/api/traces/workflows/{wf_id}/conclude', json={})
        self.assertEqual(r.status_code, 200, r.data)
        return wf_id

    def _upload(self):
        r = self.client.post('/api/traces/blobs', json={'data_url': self.PNG_DATA_URL})
        self.assertEqual(r.status_code, 200, r.data)
        return r.get_json()['sha256']

    def test_conclude_requires_title_and_pages(self):
        wf = self.client.post('/api/traces/workflows', json={'title': ''}).get_json()
        # empty title and no pages
        r = self.client.post(f'/api/traces/workflows/{wf["id"]}/conclude', json={})
        self.assertEqual(r.status_code, 400)
        # title but still no pages
        self.client.put(f'/api/traces/workflows/{wf["id"]}', json={'title': 'X'})
        r = self.client.post(f'/api/traces/workflows/{wf["id"]}/conclude', json={})
        self.assertEqual(r.status_code, 400)

    def test_workflow_lists_split_by_status(self):
        self._draft_with_pages(1, 'draftA')
        self._concluded(1, 'doneB')
        data = self.client.get('/api/traces/workflows').get_json()
        self.assertEqual([w['title'] for w in data['drafts']], ['draftA'])
        self.assertEqual([w['title'] for w in data['concluded']], ['doneB'])
        self.assertEqual(data['concluded'][0]['page_count'], 1)

    def test_blob_roundtrip_and_serve(self):
        sha = self._upload()
        r = self.client.get(f'/api/traces/blobs/{sha}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content_type, 'image/png')
        self.assertTrue(r.data.startswith(b'\x89PNG'))
        self.assertEqual(self.client.get('/api/traces/blobs/deadbeef').status_code, 404)

    def test_blob_rejects_non_image(self):
        r = self.client.post('/api/traces/blobs', json={'data_url': 'data:text/plain;base64,aGk='})
        self.assertEqual(r.status_code, 400)

    def test_seal_complete(self):
        wf_id = self._concluded(2)
        wb = self.client.post('/api/traces/workbooks', json={'workflow_id': wf_id}).get_json()
        self.assertEqual(len(wb['pages']), 2)
        sha = self._upload()
        for p in wb['pages']:
            r = self.client.put(f'/api/traces/workbooks/{wb["id"]}/pages/{p["id"]}',
                                json={'image_sha256': sha, 'notes': 'ok'})
            self.assertEqual(r.status_code, 200, r.data)
        r = self.client.post(f'/api/traces/workbooks/{wb["id"]}/seal', json={})
        self.assertEqual(r.get_json()['status'], 'complete')

    def test_seal_incomplete_lists_missing(self):
        wf_id = self._concluded(2)
        wb = self.client.post('/api/traces/workbooks', json={'workflow_id': wf_id}).get_json()
        sha = self._upload()
        self.client.put(f'/api/traces/workbooks/{wb["id"]}/pages/{wb["pages"][0]["id"]}',
                        json={'image_sha256': sha})
        r = self.client.post(f'/api/traces/workbooks/{wb["id"]}/seal', json={}).get_json()
        self.assertEqual(r['status'], 'incomplete')
        self.assertEqual(r['missing_pages'], ['P1'])

    def test_extra_page_makes_errata_and_orders_after_host(self):
        wf_id = self._concluded(2)
        wb = self.client.post('/api/traces/workbooks', json={'workflow_id': wf_id}).get_json()
        sha = self._upload()
        for p in wb['pages']:
            self.client.put(f'/api/traces/workbooks/{wb["id"]}/pages/{p["id"]}',
                            json={'image_sha256': sha})
        # insert an extra after the first page
        host = wb['pages'][0]
        r = self.client.post(f'/api/traces/workbooks/{wb["id"]}/add-extra',
                             json={'after_page_id': host['id']})
        self.assertEqual(r.status_code, 200, r.data)
        extra_id = r.get_json()['id']
        # reload: order should be P0, extra, P1
        fresh = self.client.get(f'/api/traces/workbooks/{wb["id"]}').get_json()
        order = [p['id'] for p in fresh['pages']]
        self.assertEqual(order, [wb['pages'][0]['id'], extra_id, wb['pages'][1]['id']])
        r = self.client.post(f'/api/traces/workbooks/{wb["id"]}/seal', json={}).get_json()
        self.assertEqual(r['status'], 'errata')
        self.assertTrue(r['has_extras'])

    def test_template_page_cannot_be_deleted_from_workbook(self):
        wf_id = self._concluded(1)
        wb = self.client.post('/api/traces/workbooks', json={'workflow_id': wf_id}).get_json()
        r = self.client.delete(f'/api/traces/workbooks/{wb["id"]}/pages/{wb["pages"][0]["id"]}')
        self.assertEqual(r.status_code, 400)

    def test_sealed_workbook_rejects_edits_until_reopen(self):
        wf_id = self._concluded(1)
        wb = self.client.post('/api/traces/workbooks', json={'workflow_id': wf_id}).get_json()
        sha = self._upload()
        pid = wb['pages'][0]['id']
        self.client.put(f'/api/traces/workbooks/{wb["id"]}/pages/{pid}', json={'image_sha256': sha})
        self.client.post(f'/api/traces/workbooks/{wb["id"]}/seal', json={})
        r = self.client.put(f'/api/traces/workbooks/{wb["id"]}/pages/{pid}', json={'notes': 'x'})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.client.post(f'/api/traces/workbooks/{wb["id"]}/reopen', json={}).status_code, 200)
        r = self.client.put(f'/api/traces/workbooks/{wb["id"]}/pages/{pid}', json={'notes': 'x'})
        self.assertEqual(r.status_code, 200)

    def test_concluded_template_with_runs_is_locked(self):
        wf_id = self._concluded(1)
        page = self.client.get(f'/api/traces/workflows/{wf_id}').get_json()['pages'][0]
        self.client.post('/api/traces/workbooks', json={'workflow_id': wf_id})
        # title edit, page edit, and delete all blocked
        self.assertEqual(self.client.put(f'/api/traces/workflows/{wf_id}',
                                         json={'title': 'new'}).status_code, 403)
        self.assertEqual(self.client.put(f'/api/traces/pages/{page["id"]}',
                                         json={'title': 'new'}).status_code, 403)
        self.assertEqual(self.client.delete(f'/api/traces/workflows/{wf_id}').status_code, 409)

    def test_delete_draft_workflow(self):
        wf_id = self._draft_with_pages(1)
        self.assertEqual(self.client.delete(f'/api/traces/workflows/{wf_id}').status_code, 200)
        self.assertEqual(self.client.get(f'/api/traces/workflows/{wf_id}').status_code, 404)


if __name__ == '__main__':
    unittest.main()
