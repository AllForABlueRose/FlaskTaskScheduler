import os
import shutil
from datetime import datetime
from html import escape as html_escape

from flask import Blueprint, jsonify, request, send_file

from db import db_connect
from routes.auth import login_required

applications_bp = Blueprint('applications', __name__)

SUPPORTED_EXT = {
    '.png': 'image', '.jpg': 'image', '.jpeg': 'image',
    '.gif': 'image', '.bmp': 'image', '.webp': 'image',
    '.xlsx': 'excel',
    '.docx': 'word',
    '.pdf': 'pdf',
}

MAX_EXCEL_ROWS = 500
APPROVED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'approved')


def _file_type(name):
    ext = os.path.splitext(name)[1].lower()
    return SUPPORTED_EXT.get(ext)


def _file_mtime_iso(filepath):
    try:
        return datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
    except OSError:
        return None



@applications_bp.route('/api/applications/files')
@login_required
def list_files():
    folder = (request.args.get('folder') or '').strip()
    if not folder:
        return jsonify({'error': 'folder parameter required'}), 400
    if not os.path.isdir(folder):
        return jsonify({'error': 'not a valid directory'}), 400
    try:
        entries = os.listdir(folder)
    except PermissionError:
        return jsonify({'error': 'permission denied'}), 403

    disk_files = {}
    for name in sorted(entries):
        ftype = _file_type(name)
        if ftype and os.path.isfile(os.path.join(folder, name)):
            disk_files[name] = ftype

    with db_connect() as conn:
        rows = conn.execute(
            'SELECT id, filename, status, file_mtime FROM app_file_status '
            'WHERE folder=? ORDER BY created_at ASC', (folder,)
        ).fetchall()

    dismissed = set()
    flagged = {}
    rejected = []
    approved = set()
    for r in rows:
        if r['status'] == 'dismissed':
            dismissed.add(r['filename'])
        elif r['status'] == 'flagged':
            flagged[r['filename']] = {'id': r['id'], 'mtime': r['file_mtime']}
        elif r['status'] == 'rejected':
            rejected.append({'id': r['id'], 'filename': r['filename'], 'mtime': r['file_mtime']})
        elif r['status'] == 'approved':
            approved.add(r['filename'])

    stale_flag_ids = []
    for name, info in list(flagged.items()):
        if name in disk_files:
            current_mtime = _file_mtime_iso(os.path.join(folder, name))
            if current_mtime and current_mtime != info['mtime']:
                stale_flag_ids.append(info['id'])
                del flagged[name]
    if stale_flag_ids:
        with db_connect() as conn:
            for sid in stale_flag_ids:
                conn.execute('DELETE FROM app_file_status WHERE id=?', (sid,))

    files = []
    handled_by_reject = set()

    for rej in rejected:
        name = rej['filename']
        ftype = _file_type(name) or 'pdf'
        if name in disk_files:
            current_mtime = _file_mtime_iso(os.path.join(folder, name))
            if current_mtime == rej['mtime']:
                handled_by_reject.add(name)
            else:
                files.append({'name': name, 'type': ftype, 'status': 'rejected', 'ghost': True})
        else:
            files.append({'name': name, 'type': ftype, 'status': 'rejected', 'ghost': True})

    for name, ftype in disk_files.items():
        if name in dismissed:
            continue
        if name in handled_by_reject:
            files.append({'name': name, 'type': ftype, 'status': 'rejected'})
            continue
        entry = {'name': name, 'type': ftype}
        if name in approved:
            entry['status'] = 'approved'
        elif name in flagged:
            entry['status'] = 'flagged'
        files.append(entry)

    files.sort(key=lambda f: (f.get('ghost', False), f['name'].lower()))
    return jsonify({'files': files, 'folder': folder})


@applications_bp.route('/api/applications/file/status', methods=['POST'])
@login_required
def set_file_status():
    data = request.json or {}
    folder = (data.get('folder') or '').strip()
    filename = (data.get('filename') or '').strip()
    status = (data.get('status') or '').strip()
    if not folder or not filename or status not in ('dismissed', 'flagged', 'rejected', 'approved'):
        return jsonify({'error': 'folder, filename, and valid status required'}), 400

    filepath = os.path.join(folder, filename)
    mtime = _file_mtime_iso(filepath)

    approved_path = None
    if status == 'approved':
        if not os.path.isfile(filepath):
            return jsonify({'error': 'file not found'}), 404
        grandparent = os.path.basename(os.path.dirname(folder))
        parent = os.path.basename(folder)
        if not grandparent:
            grandparent = '_root'
        dest_dir = os.path.join(APPROVED_DIR, grandparent, parent)
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(filepath, os.path.join(dest_dir, filename))
        approved_path = os.path.join(grandparent, parent, filename)

    with db_connect() as conn:
        if status in ('dismissed', 'flagged'):
            conn.execute(
                'DELETE FROM app_file_status WHERE folder=? AND filename=? AND status IN (?, ?)',
                (folder, filename, 'dismissed', 'flagged')
            )
        conn.execute(
            'INSERT INTO app_file_status (folder, filename, status, file_mtime, created_at, approved_path) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (folder, filename, status, mtime, datetime.now().isoformat(), approved_path)
        )
    return jsonify({'ok': True})


@applications_bp.route('/api/applications/approved-tree')
@login_required
def approved_tree():
    tree = []
    if not os.path.isdir(APPROVED_DIR):
        return jsonify({'tree': tree})

    with db_connect() as conn:
        rows = conn.execute(
            "SELECT approved_path, created_at FROM app_file_status WHERE status='approved' AND approved_path IS NOT NULL"
        ).fetchall()
    approved_dates = {r['approved_path']: r['created_at'] for r in rows}

    for gp_name in sorted(os.listdir(APPROVED_DIR)):
        gp_path = os.path.join(APPROVED_DIR, gp_name)
        if not os.path.isdir(gp_path):
            continue
        gp_node = {'name': gp_name, 'children': [], 'last_updated': None}
        for p_name in sorted(os.listdir(gp_path)):
            p_path = os.path.join(gp_path, p_name)
            if not os.path.isdir(p_path):
                continue
            p_node = {'name': p_name, 'children': [], 'last_updated': None}
            for fname in sorted(os.listdir(p_path)):
                ftype = _file_type(fname)
                if ftype and os.path.isfile(os.path.join(p_path, fname)):
                    ap = os.path.join(gp_name, p_name, fname)
                    approved_at = approved_dates.get(ap)
                    p_node['children'].append({'name': fname, 'type': ftype, 'approved_at': approved_at})
                    if approved_at and (not p_node['last_updated'] or approved_at > p_node['last_updated']):
                        p_node['last_updated'] = approved_at
            if p_node['children']:
                gp_node['children'].append(p_node)
                if p_node['last_updated'] and (not gp_node['last_updated'] or p_node['last_updated'] > gp_node['last_updated']):
                    gp_node['last_updated'] = p_node['last_updated']
        if gp_node['children']:
            tree.append(gp_node)
    return jsonify({'tree': tree})


def _safe_path(folder, name):
    joined = os.path.join(folder, name)
    real = os.path.realpath(joined)
    if not real.startswith(os.path.realpath(folder)):
        return None
    return real


@applications_bp.route('/api/applications/file/preview')
@login_required
def file_preview():
    folder = (request.args.get('folder') or '').strip()
    name = (request.args.get('name') or '').strip()
    if not folder or not name:
        return jsonify({'error': 'folder and name required'}), 400

    if request.args.get('approved') == '1':
        base = os.path.join(APPROVED_DIR, folder)
        filepath = _safe_path(base, name)
        if filepath is None or not filepath.startswith(os.path.realpath(APPROVED_DIR)):
            return jsonify({'error': 'forbidden'}), 403
    else:
        filepath = _safe_path(folder, name)
        if filepath is None:
            return jsonify({'error': 'forbidden'}), 403
    if not os.path.isfile(filepath):
        return jsonify({'error': 'file not found'}), 404

    ftype = _file_type(name)
    if not ftype:
        return jsonify({'error': 'unsupported file type'}), 400

    if ftype == 'image':
        return _preview_image(filepath)
    if ftype == 'pdf':
        return _preview_pdf(filepath)
    if ftype == 'excel':
        page = request.args.get('page', '0')
        try:
            page = max(0, int(page))
        except ValueError:
            page = 0
        return _preview_excel(filepath, page)
    if ftype == 'word':
        return _preview_word(filepath)
    return jsonify({'error': 'unsupported'}), 400


def _preview_image(filepath):
    import mimetypes
    mime = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
    return send_file(filepath, mimetype=mime)


def _preview_pdf(filepath):
    return send_file(filepath, mimetype='application/pdf')


def _preview_excel(filepath, page):
    import openpyxl
    try:
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    except Exception:
        return jsonify({'error': 'cannot read Excel file'}), 400
    try:
        sheets = wb.sheetnames
        if not sheets:
            return jsonify({'error': 'no sheets found'}), 400
        page = min(page, len(sheets) - 1)
        ws = wb[sheets[page]]

        rows = []
        for r in ws.iter_rows(values_only=True):
            row = []
            for cell in r:
                if cell is None:
                    row.append('')
                elif isinstance(cell, datetime):
                    row.append(cell.isoformat())
                else:
                    row.append(str(cell))
            rows.append(row)

        truncated = len(rows) > MAX_EXCEL_ROWS
        if truncated:
            rows = rows[:MAX_EXCEL_ROWS]

        headers = rows[0] if rows else []
        data_rows = rows[1:] if rows else []

        return jsonify({
            'type': 'excel',
            'page': page,
            'total_pages': len(sheets),
            'page_label': sheets[page],
            'headers': headers,
            'rows': data_rows,
            'truncated': truncated,
        })
    finally:
        wb.close()


def _preview_word(filepath):
    import docx
    from docx.oxml.ns import qn
    try:
        doc = docx.Document(filepath)
    except Exception:
        return jsonify({'error': 'cannot read Word file'}), 400

    parts = []
    for child in doc.element.body:
        if child.tag == qn('w:p'):
            para = docx.text.paragraph.Paragraph(child, doc)
            parts.append(_paragraph_to_html(para))
        elif child.tag == qn('w:tbl'):
            table = docx.table.Table(child, doc)
            parts.append(_table_to_html(table))

    return jsonify({
        'type': 'word',
        'page': 0,
        'total_pages': 1,
        'html': '\n'.join(parts),
    })


def _paragraph_to_html(para):
    style_name = (para.style.name or '').lower()
    tag = 'p'
    for level in range(1, 7):
        if style_name == f'heading {level}':
            tag = f'h{level}'
            break

    runs_html = []
    for run in para.runs:
        text = html_escape(run.text)
        if run.bold:
            text = f'<strong>{text}</strong>'
        if run.italic:
            text = f'<em>{text}</em>'
        if run.underline:
            text = f'<u>{text}</u>'
        runs_html.append(text)

    inner = ''.join(runs_html)
    if not inner.strip():
        return '<p>&nbsp;</p>'
    return f'<{tag}>{inner}</{tag}>'


def _table_to_html(table):
    rows_html = []
    for row in table.rows:
        cells = ''.join(
            f'<td>{html_escape(cell.text)}</td>' for cell in row.cells
        )
        rows_html.append(f'<tr>{cells}</tr>')
    return f'<table class="app-docx-table">{"".join(rows_html)}</table>'
