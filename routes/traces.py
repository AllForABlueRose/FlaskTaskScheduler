"""Traces: scrapbook-style guided image collection.

A *workflow* is a reusable template -- an ordered set of pages, each with a
fixed title, an explanation of what image belongs there, and an optional sample
image. Once concluded, a workflow can be run as a *workbook*: the operator goes
page by page pasting the required image and adding notes. Sealing a workbook
runs a completeness check that classifies it complete / incomplete / errata.

Images are stored as content-addressed blobs in `trace_blobs` (dedup by
SHA-256), mirroring the ledger blob store but kept in the operational DB. The
client compresses images to JPEG before upload; this module only decodes,
size-checks, and stores them.
"""

import base64
import hashlib
import io
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file

from db import db_connect
from routes.auth import login_required

traces_bp = Blueprint('traces', __name__)

MAX_BLOB_BYTES = 5 * 1024 * 1024


def _now():
    return datetime.now().isoformat()


def _clean(value):
    return str(value).strip() if value is not None else ''


# --- blob store (content-addressed, mirrors ledger.store_blob/fetch_blob) ---

def store_blob(conn, content):
    sha = hashlib.sha256(content).hexdigest()
    conn.execute(
        'INSERT OR IGNORE INTO trace_blobs (content_sha256, content, size, created_at) '
        'VALUES (?, ?, ?, ?)',
        (sha, content, len(content), _now())
    )
    return sha


def fetch_blob(conn, sha):
    row = conn.execute(
        'SELECT content FROM trace_blobs WHERE content_sha256=?', (sha,)
    ).fetchone()
    return row['content'] if row else None


def _blob_url(sha):
    return ('/api/traces/blobs/' + sha) if sha else None


def _has_workbooks(conn, workflow_id):
    return conn.execute(
        'SELECT 1 FROM trace_workbooks WHERE workflow_id=? LIMIT 1', (workflow_id,)
    ).fetchone() is not None


# --- workflow templates ---

@traces_bp.route('/api/traces/workflows')
@login_required
def list_workflows():
    with db_connect() as conn:
        rows = conn.execute(
            'SELECT w.id, w.title, w.status, w.created_at, w.concluded_at, '
            '       (SELECT COUNT(*) FROM trace_workflow_pages p WHERE p.workflow_id=w.id) AS page_count '
            'FROM trace_workflows w ORDER BY w.created_at ASC'
        ).fetchall()
    drafts, concluded = [], []
    for r in rows:
        (concluded if r['status'] == 'concluded' else drafts).append(dict(r))
    return jsonify({'drafts': drafts, 'concluded': concluded})


def _workflow_payload(conn, workflow_id):
    wf = conn.execute('SELECT * FROM trace_workflows WHERE id=?', (workflow_id,)).fetchone()
    if not wf:
        return None
    pages = conn.execute(
        'SELECT id, title, explanation, sample_sha256, position FROM trace_workflow_pages '
        'WHERE workflow_id=? ORDER BY position ASC, created_at ASC', (workflow_id,)
    ).fetchall()
    out = dict(wf)
    out['pages'] = [{**dict(p), 'sample_url': _blob_url(p['sample_sha256'])} for p in pages]
    return out


@traces_bp.route('/api/traces/workflows', methods=['POST'])
@login_required
def create_workflow():
    title = _clean((request.json or {}).get('title'))
    wf_id = str(uuid.uuid4())
    with db_connect() as conn:
        conn.execute(
            'INSERT INTO trace_workflows (id, title, status, created_at) VALUES (?, ?, ?, ?)',
            (wf_id, title, 'draft', _now())
        )
        payload = _workflow_payload(conn, wf_id)
    return jsonify(payload)


@traces_bp.route('/api/traces/workflows/<workflow_id>')
@login_required
def get_workflow(workflow_id):
    with db_connect() as conn:
        payload = _workflow_payload(conn, workflow_id)
    if payload is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(payload)


@traces_bp.route('/api/traces/workflows/<workflow_id>', methods=['PUT'])
@login_required
def update_workflow(workflow_id):
    title = _clean((request.json or {}).get('title'))
    with db_connect() as conn:
        wf = conn.execute('SELECT status FROM trace_workflows WHERE id=?', (workflow_id,)).fetchone()
        if not wf:
            return jsonify({'error': 'not found'}), 404
        if wf['status'] == 'concluded' and _has_workbooks(conn, workflow_id):
            return jsonify({'error': 'concluded workflow with runs is locked'}), 403
        conn.execute('UPDATE trace_workflows SET title=? WHERE id=?', (title, workflow_id))
    return jsonify({'ok': True})


@traces_bp.route('/api/traces/workflows/<workflow_id>', methods=['DELETE'])
@login_required
def delete_workflow(workflow_id):
    with db_connect() as conn:
        wf = conn.execute('SELECT 1 FROM trace_workflows WHERE id=?', (workflow_id,)).fetchone()
        if not wf:
            return jsonify({'error': 'not found'}), 404
        if _has_workbooks(conn, workflow_id):
            return jsonify({'error': 'workflow has runs'}), 409
        conn.execute('DELETE FROM trace_workflow_pages WHERE workflow_id=?', (workflow_id,))
        conn.execute('DELETE FROM trace_workflows WHERE id=?', (workflow_id,))
    return jsonify({'ok': True})


@traces_bp.route('/api/traces/workflows/<workflow_id>/conclude', methods=['POST'])
@login_required
def conclude_workflow(workflow_id):
    with db_connect() as conn:
        wf = conn.execute('SELECT title FROM trace_workflows WHERE id=?', (workflow_id,)).fetchone()
        if not wf:
            return jsonify({'error': 'not found'}), 404
        if not _clean(wf['title']):
            return jsonify({'error': 'title required'}), 400
        n = conn.execute(
            'SELECT COUNT(*) AS c FROM trace_workflow_pages WHERE workflow_id=?', (workflow_id,)
        ).fetchone()['c']
        if n == 0:
            return jsonify({'error': 'at least one page required'}), 400
        conn.execute(
            'UPDATE trace_workflows SET status=?, concluded_at=? WHERE id=?',
            ('concluded', _now(), workflow_id)
        )
    return jsonify({'status': 'concluded'})


# --- template pages ---

def _assert_template_editable(conn, workflow_id):
    """Return an error response tuple if the parent template is locked, else None."""
    wf = conn.execute('SELECT status FROM trace_workflows WHERE id=?', (workflow_id,)).fetchone()
    if not wf:
        return jsonify({'error': 'not found'}), 404
    if wf['status'] == 'concluded' and _has_workbooks(conn, workflow_id):
        return jsonify({'error': 'concluded workflow with runs is locked'}), 403
    return None


@traces_bp.route('/api/traces/workflows/<workflow_id>/pages', methods=['POST'])
@login_required
def create_page(workflow_id):
    data = request.json or {}
    page_id = str(uuid.uuid4())
    with db_connect() as conn:
        err = _assert_template_editable(conn, workflow_id)
        if err:
            return err
        nxt = conn.execute(
            'SELECT COALESCE(MAX(position), -1) + 1 AS p FROM trace_workflow_pages WHERE workflow_id=?',
            (workflow_id,)
        ).fetchone()['p']
        conn.execute(
            'INSERT INTO trace_workflow_pages '
            '(id, workflow_id, title, explanation, sample_sha256, position, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (page_id, workflow_id, _clean(data.get('title')), _clean(data.get('explanation')) or None,
             _clean(data.get('sample_sha256')) or None, nxt, _now())
        )
        row = conn.execute(
            'SELECT id, title, explanation, sample_sha256, position FROM trace_workflow_pages WHERE id=?',
            (page_id,)
        ).fetchone()
    return jsonify({**dict(row), 'sample_url': _blob_url(row['sample_sha256'])})


@traces_bp.route('/api/traces/pages/<page_id>', methods=['PUT'])
@login_required
def update_page(page_id):
    data = request.json or {}
    with db_connect() as conn:
        page = conn.execute(
            'SELECT workflow_id FROM trace_workflow_pages WHERE id=?', (page_id,)
        ).fetchone()
        if not page:
            return jsonify({'error': 'not found'}), 404
        err = _assert_template_editable(conn, page['workflow_id'])
        if err:
            return err
        fields, values = [], []
        if 'title' in data:
            fields.append('title=?'); values.append(_clean(data.get('title')))
        if 'explanation' in data:
            fields.append('explanation=?'); values.append(_clean(data.get('explanation')) or None)
        if 'sample_sha256' in data:
            fields.append('sample_sha256=?'); values.append(_clean(data.get('sample_sha256')) or None)
        if fields:
            values.append(page_id)
            conn.execute(f'UPDATE trace_workflow_pages SET {", ".join(fields)} WHERE id=?', values)
        row = conn.execute(
            'SELECT id, title, explanation, sample_sha256, position FROM trace_workflow_pages WHERE id=?',
            (page_id,)
        ).fetchone()
    return jsonify({**dict(row), 'sample_url': _blob_url(row['sample_sha256'])})


@traces_bp.route('/api/traces/pages/<page_id>', methods=['DELETE'])
@login_required
def delete_page(page_id):
    with db_connect() as conn:
        page = conn.execute(
            'SELECT workflow_id FROM trace_workflow_pages WHERE id=?', (page_id,)
        ).fetchone()
        if not page:
            return jsonify({'error': 'not found'}), 404
        err = _assert_template_editable(conn, page['workflow_id'])
        if err:
            return err
        workflow_id = page['workflow_id']
        conn.execute('DELETE FROM trace_workflow_pages WHERE id=?', (page_id,))
        remaining = conn.execute(
            'SELECT id FROM trace_workflow_pages WHERE workflow_id=? ORDER BY position ASC, created_at ASC',
            (workflow_id,)
        ).fetchall()
        for pos, r in enumerate(remaining):
            conn.execute('UPDATE trace_workflow_pages SET position=? WHERE id=?', (pos, r['id']))
    return jsonify({'ok': True})


# --- workbooks (runs) ---

@traces_bp.route('/api/traces/workbooks')
@login_required
def list_workbooks():
    with db_connect() as conn:
        rows = conn.execute(
            'SELECT id, workflow_id, title, status, has_extras, created_at, sealed_at '
            'FROM trace_workbooks ORDER BY created_at DESC'
        ).fetchall()
    return jsonify([dict(r) for r in rows])


def _workbook_payload(conn, workbook_id):
    wb = conn.execute('SELECT * FROM trace_workbooks WHERE id=?', (workbook_id,)).fetchone()
    if not wb:
        return None
    pages = conn.execute(
        'SELECT id, source_page_id, kind, title, explanation, image_sha256, notes, '
        '       base_position, sub_position FROM trace_workbook_pages '
        'WHERE workbook_id=? ORDER BY base_position ASC, sub_position ASC, created_at ASC',
        (workbook_id,)
    ).fetchall()
    # sample images come live from the source template page
    sample_by_src = {}
    src_ids = [p['source_page_id'] for p in pages if p['source_page_id']]
    if src_ids:
        placeholders = ','.join('?' * len(src_ids))
        for r in conn.execute(
            f'SELECT id, sample_sha256 FROM trace_workflow_pages WHERE id IN ({placeholders})',
            src_ids
        ).fetchall():
            sample_by_src[r['id']] = r['sample_sha256']
    out = dict(wb)
    out['pages'] = [{
        **dict(p),
        'image_url': _blob_url(p['image_sha256']),
        'sample_url': _blob_url(sample_by_src.get(p['source_page_id'])),
    } for p in pages]
    return out


@traces_bp.route('/api/traces/workbooks', methods=['POST'])
@login_required
def create_workbook():
    workflow_id = _clean((request.json or {}).get('workflow_id'))
    wb_id = str(uuid.uuid4())
    with db_connect() as conn:
        wf = conn.execute(
            'SELECT title, status FROM trace_workflows WHERE id=?', (workflow_id,)
        ).fetchone()
        if not wf:
            return jsonify({'error': 'workflow not found'}), 404
        if wf['status'] != 'concluded':
            return jsonify({'error': 'workflow not concluded'}), 400
        now = _now()
        conn.execute(
            'INSERT INTO trace_workbooks (id, workflow_id, title, status, created_at, last_opened_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (wb_id, workflow_id, wf['title'], 'in_progress', now, now)
        )
        tpages = conn.execute(
            'SELECT id, title, explanation, position FROM trace_workflow_pages '
            'WHERE workflow_id=? ORDER BY position ASC, created_at ASC', (workflow_id,)
        ).fetchall()
        for tp in tpages:
            conn.execute(
                'INSERT INTO trace_workbook_pages '
                '(id, workbook_id, source_page_id, kind, title, explanation, '
                ' base_position, sub_position, created_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (str(uuid.uuid4()), wb_id, tp['id'], 'template', tp['title'], tp['explanation'],
                 tp['position'], 0, _now())
            )
        payload = _workbook_payload(conn, wb_id)
    return jsonify(payload)


@traces_bp.route('/api/traces/workbooks/<workbook_id>')
@login_required
def get_workbook(workbook_id):
    with db_connect() as conn:
        conn.execute(
            'UPDATE trace_workbooks SET last_opened_at=? WHERE id=?', (_now(), workbook_id)
        )
        payload = _workbook_payload(conn, workbook_id)
    if payload is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(payload)


@traces_bp.route('/api/traces/workbooks/<workbook_id>/pages/<page_id>', methods=['PUT'])
@login_required
def save_workbook_page(workbook_id, page_id):
    data = request.json or {}
    with db_connect() as conn:
        wb = conn.execute('SELECT status FROM trace_workbooks WHERE id=?', (workbook_id,)).fetchone()
        if not wb:
            return jsonify({'error': 'not found'}), 404
        if wb['status'] not in ('in_progress', 'incomplete'):
            return jsonify({'error': 'workbook is sealed; reopen to edit'}), 409
        page = conn.execute(
            'SELECT kind FROM trace_workbook_pages WHERE id=? AND workbook_id=?',
            (page_id, workbook_id)
        ).fetchone()
        if not page:
            return jsonify({'error': 'page not found'}), 404
        fields, values = [], []
        if 'image_sha256' in data:
            fields.append('image_sha256=?'); values.append(_clean(data.get('image_sha256')) or None)
        if 'notes' in data:
            fields.append('notes=?'); values.append(_clean(data.get('notes')) or None)
        if page['kind'] == 'extra':
            if 'title' in data:
                fields.append('title=?'); values.append(_clean(data.get('title')))
            if 'explanation' in data:
                fields.append('explanation=?'); values.append(_clean(data.get('explanation')) or None)
        if fields:
            values.extend([page_id, workbook_id])
            conn.execute(
                f'UPDATE trace_workbook_pages SET {", ".join(fields)} WHERE id=? AND workbook_id=?',
                values
            )
        row = conn.execute(
            'SELECT id, source_page_id, kind, title, explanation, image_sha256, notes, '
            '       base_position, sub_position FROM trace_workbook_pages WHERE id=?', (page_id,)
        ).fetchone()
    return jsonify({**dict(row), 'image_url': _blob_url(row['image_sha256'])})


@traces_bp.route('/api/traces/workbooks/<workbook_id>/add-extra', methods=['POST'])
@login_required
def add_extra_page(workbook_id):
    after_page_id = _clean((request.json or {}).get('after_page_id'))
    new_id = str(uuid.uuid4())
    with db_connect() as conn:
        wb = conn.execute('SELECT status FROM trace_workbooks WHERE id=?', (workbook_id,)).fetchone()
        if not wb:
            return jsonify({'error': 'not found'}), 404
        if wb['status'] not in ('in_progress', 'incomplete'):
            return jsonify({'error': 'workbook is sealed; reopen to edit'}), 409
        after = conn.execute(
            'SELECT base_position FROM trace_workbook_pages WHERE id=? AND workbook_id=?',
            (after_page_id, workbook_id)
        ).fetchone()
        if not after:
            return jsonify({'error': 'after_page not found'}), 404
        base = after['base_position']
        nxt_sub = conn.execute(
            'SELECT COALESCE(MAX(sub_position), 0) + 1 AS s FROM trace_workbook_pages '
            'WHERE workbook_id=? AND base_position=?', (workbook_id, base)
        ).fetchone()['s']
        conn.execute(
            'INSERT INTO trace_workbook_pages '
            '(id, workbook_id, source_page_id, kind, title, explanation, '
            ' base_position, sub_position, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (new_id, workbook_id, None, 'extra', 'Extra page', None, base, nxt_sub, _now())
        )
        conn.execute('UPDATE trace_workbooks SET has_extras=1 WHERE id=?', (workbook_id,))
        row = conn.execute(
            'SELECT id, source_page_id, kind, title, explanation, image_sha256, notes, '
            '       base_position, sub_position FROM trace_workbook_pages WHERE id=?', (new_id,)
        ).fetchone()
    return jsonify({**dict(row), 'image_url': None, 'sample_url': None})


@traces_bp.route('/api/traces/workbooks/<workbook_id>/pages/<page_id>', methods=['DELETE'])
@login_required
def delete_workbook_page(workbook_id, page_id):
    with db_connect() as conn:
        wb = conn.execute('SELECT status FROM trace_workbooks WHERE id=?', (workbook_id,)).fetchone()
        if not wb:
            return jsonify({'error': 'not found'}), 404
        if wb['status'] not in ('in_progress', 'incomplete'):
            return jsonify({'error': 'workbook is sealed; reopen to edit'}), 409
        page = conn.execute(
            'SELECT kind FROM trace_workbook_pages WHERE id=? AND workbook_id=?',
            (page_id, workbook_id)
        ).fetchone()
        if not page:
            return jsonify({'error': 'page not found'}), 404
        if page['kind'] != 'extra':
            return jsonify({'error': 'only extra pages can be deleted'}), 400
        conn.execute('DELETE FROM trace_workbook_pages WHERE id=?', (page_id,))
        still = conn.execute(
            "SELECT 1 FROM trace_workbook_pages WHERE workbook_id=? AND kind='extra' LIMIT 1",
            (workbook_id,)
        ).fetchone()
        conn.execute(
            'UPDATE trace_workbooks SET has_extras=? WHERE id=?',
            (1 if still else 0, workbook_id)
        )
    return jsonify({'ok': True})


@traces_bp.route('/api/traces/workbooks/<workbook_id>/seal', methods=['POST'])
@login_required
def seal_workbook(workbook_id):
    with db_connect() as conn:
        wb = conn.execute('SELECT 1 FROM trace_workbooks WHERE id=?', (workbook_id,)).fetchone()
        if not wb:
            return jsonify({'error': 'not found'}), 404
        missing = conn.execute(
            "SELECT title FROM trace_workbook_pages "
            "WHERE workbook_id=? AND kind='template' AND (image_sha256 IS NULL OR image_sha256='') "
            "ORDER BY base_position ASC", (workbook_id,)
        ).fetchall()
        extras = conn.execute(
            "SELECT COUNT(*) AS c FROM trace_workbook_pages WHERE workbook_id=? AND kind='extra'",
            (workbook_id,)
        ).fetchone()['c']
        if missing:
            status = 'incomplete'
        elif extras > 0:
            status = 'errata'
        else:
            status = 'complete'
        conn.execute(
            'UPDATE trace_workbooks SET status=?, has_extras=?, sealed_at=? WHERE id=?',
            (status, 1 if extras > 0 else 0, _now(), workbook_id)
        )
    return jsonify({
        'status': status,
        'missing_pages': [m['title'] for m in missing],
        'has_extras': extras > 0,
    })


@traces_bp.route('/api/traces/workbooks/<workbook_id>/reopen', methods=['POST'])
@login_required
def reopen_workbook(workbook_id):
    with db_connect() as conn:
        wb = conn.execute('SELECT 1 FROM trace_workbooks WHERE id=?', (workbook_id,)).fetchone()
        if not wb:
            return jsonify({'error': 'not found'}), 404
        conn.execute(
            'UPDATE trace_workbooks SET status=?, sealed_at=NULL, last_opened_at=? WHERE id=?',
            ('in_progress', _now(), workbook_id)
        )
    return jsonify({'status': 'in_progress'})


# --- blobs ---

@traces_bp.route('/api/traces/blobs', methods=['POST'])
@login_required
def upload_blob():
    data_url = _clean((request.json or {}).get('data_url'))
    if not data_url.startswith('data:image/'):
        return jsonify({'error': 'image data url required'}), 400
    try:
        header, b64 = data_url.split(',', 1)
        content = base64.b64decode(b64)
    except (ValueError, base64.binascii.Error):
        return jsonify({'error': 'invalid data url'}), 400
    if 'image/jpeg' not in header and 'image/png' not in header:
        return jsonify({'error': 'only jpeg or png supported'}), 400
    if not content:
        return jsonify({'error': 'empty image'}), 400
    if len(content) > MAX_BLOB_BYTES:
        return jsonify({'error': 'image too large'}), 413
    with db_connect() as conn:
        sha = store_blob(conn, content)
    return jsonify({'sha256': sha, 'size': len(content)})


@traces_bp.route('/api/traces/blobs/<sha256>')
@login_required
def serve_blob(sha256):
    with db_connect() as conn:
        content = fetch_blob(conn, sha256)
    if content is None:
        return jsonify({'error': 'not found'}), 404
    mime = 'image/png' if content[:8] == b'\x89PNG\r\n\x1a\n' else 'image/jpeg'
    resp = send_file(io.BytesIO(content), mimetype=mime)
    resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return resp
