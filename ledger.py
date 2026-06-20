"""Hash-chained approval ledger backed by a dedicated SQLite blob store.

Approved file content lives in `approved_blobs`, addressed by its SHA-256 —
editing a blob breaks `sha256(content) == content_sha256` and is detected on
read. Approval events live in `approval_ledger`, where each entry's
`entry_hash` covers all its fields plus the previous entry's hash, so any
row edit or deletion breaks the chain from that point forward (git-style
tamper evidence, verified by `verify_chain`).

Kept separate from scheduler.db so blob data stays out of the operational
DB and can be backed up (or made read-only between writes) independently.
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

APPROVALS_DB = 'approvals.db'
GENESIS_HASH = '0' * 64


@contextmanager
def ledger_connect():
    conn = sqlite3.connect(APPROVALS_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_ledger_db():
    conn = sqlite3.connect(APPROVALS_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS approved_blobs(
            content_sha256 TEXT PRIMARY KEY,
            content BLOB NOT NULL,
            size INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS approval_ledger(
            seq INTEGER PRIMARY KEY,
            folder TEXT NOT NULL,
            filename TEXT NOT NULL,
            approved_path TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            size INTEGER NOT NULL,
            file_mtime TEXT,
            approved_by TEXT,
            created_at TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_approval_ledger_folder ON approval_ledger(folder)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_approval_ledger_path ON approval_ledger(approved_path)')
    conn.commit()
    conn.close()


def compute_entry_hash(seq, folder, filename, approved_path, content_sha256,
                       size, file_mtime, approved_by, created_at, prev_hash):
    # Canonical serialization: a JSON array of strings, no whitespace. Any
    # change to the serialization scheme invalidates existing chains.
    payload = json.dumps([
        str(seq), folder, filename, approved_path, content_sha256,
        str(size), file_mtime or '', approved_by or '', created_at, prev_hash,
    ], separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def store_blob(conn, content, created_at=None):
    sha = hashlib.sha256(content).hexdigest()
    conn.execute(
        'INSERT OR IGNORE INTO approved_blobs (content_sha256, content, size, created_at) '
        'VALUES (?, ?, ?, ?)',
        (sha, content, len(content), created_at or datetime.now().isoformat())
    )
    return sha


def fetch_blob(conn, content_sha256):
    row = conn.execute(
        'SELECT content FROM approved_blobs WHERE content_sha256=?', (content_sha256,)
    ).fetchone()
    return row['content'] if row else None


def append_entry(conn, folder, filename, approved_path, content,
                 file_mtime=None, approved_by=None, created_at=None):
    created_at = created_at or datetime.now().isoformat()
    sha = store_blob(conn, content, created_at)
    head = conn.execute(
        'SELECT seq, entry_hash FROM approval_ledger ORDER BY seq DESC LIMIT 1'
    ).fetchone()
    seq = (head['seq'] + 1) if head else 1
    prev_hash = head['entry_hash'] if head else GENESIS_HASH
    entry_hash = compute_entry_hash(
        seq, folder, filename, approved_path, sha,
        len(content), file_mtime, approved_by, created_at, prev_hash
    )
    conn.execute(
        'INSERT INTO approval_ledger '
        '(seq, folder, filename, approved_path, content_sha256, size, file_mtime, '
        ' approved_by, created_at, prev_hash, entry_hash) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (seq, folder, filename, approved_path, sha, len(content), file_mtime,
         approved_by, created_at, prev_hash, entry_hash)
    )
    return {'seq': seq, 'content_sha256': sha, 'entry_hash': entry_hash}


def latest_hashes_for_folder(conn, folder):
    """filename -> content_sha256 of the most recent approval in this folder."""
    rows = conn.execute(
        'SELECT filename, content_sha256 FROM approval_ledger WHERE folder=? ORDER BY seq ASC',
        (folder,)
    ).fetchall()
    return {r['filename']: r['content_sha256'] for r in rows}


def latest_entry_for_path(conn, approved_path):
    return conn.execute(
        'SELECT * FROM approval_ledger WHERE approved_path=? ORDER BY seq DESC LIMIT 1',
        (approved_path,)
    ).fetchone()


def latest_entries_by_path(conn):
    """approved_path -> most recent ledger row, for building the approved tree."""
    rows = conn.execute(
        'SELECT approved_path, content_sha256, created_at FROM approval_ledger ORDER BY seq ASC'
    ).fetchall()
    return {r['approved_path']: r for r in rows}


def verify_chain(conn, include_blobs=True):
    """Walk the full chain; recompute every entry hash and check linkage.

    Returns {'ok': bool, 'entries': int, 'blobs': int, 'errors': [str]}.
    """
    errors = []
    rows = conn.execute('SELECT * FROM approval_ledger ORDER BY seq ASC').fetchall()
    prev_hash = GENESIS_HASH
    expected_seq = 1
    for r in rows:
        if r['seq'] != expected_seq:
            errors.append(f"entry {r['seq']}: sequence gap (expected {expected_seq} - entries deleted?)")
            expected_seq = r['seq']
        if r['prev_hash'] != prev_hash:
            errors.append(f"entry {r['seq']}: broken chain linkage")
        recomputed = compute_entry_hash(
            r['seq'], r['folder'], r['filename'], r['approved_path'],
            r['content_sha256'], r['size'], r['file_mtime'],
            r['approved_by'], r['created_at'], r['prev_hash']
        )
        if recomputed != r['entry_hash']:
            errors.append(f"entry {r['seq']}: entry hash mismatch (row was modified)")
        prev_hash = r['entry_hash']
        expected_seq += 1

    blob_count = 0
    if include_blobs:
        referenced = {r['content_sha256'] for r in rows}
        blobs = conn.execute('SELECT content_sha256, content FROM approved_blobs').fetchall()
        blob_count = len(blobs)
        stored = set()
        for b in blobs:
            stored.add(b['content_sha256'])
            if hashlib.sha256(b['content']).hexdigest() != b['content_sha256']:
                errors.append(f"blob {b['content_sha256'][:12]}...: content does not match its hash (blob was modified)")
        for sha in sorted(referenced - stored):
            errors.append(f"blob {sha[:12]}...: referenced by ledger but missing from blob store")

    return {'ok': not errors, 'entries': len(rows), 'blobs': blob_count, 'errors': errors}
