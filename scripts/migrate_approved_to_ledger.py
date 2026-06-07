"""One-time migration: ingest the legacy `approved/` folder into the approval ledger.

Reads every supported file under approved/<grandparent>/<parent>/<filename>,
stores its content in the blob store, and appends a hash-chained ledger entry.
Approval metadata (original source folder, approval date, mtime) is recovered
from scheduler.db's app_file_status rows where possible; copies with no DB
record are ingested as orphans (folder unknown) so no content is lost.

The script never deletes anything. The approved/ folder is left untouched —
remove it manually once the migration has been verified.

Usage:
    python3 scripts/migrate_approved_to_ledger.py --dry-run   # show the plan
    python3 scripts/migrate_approved_to_ledger.py             # migrate
    python3 scripts/migrate_approved_to_ledger.py --verify-only

Idempotency: refuses to run against a non-empty ledger unless --append is
given, so re-running by accident cannot duplicate entries.
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import ledger
from routes.applications import SUPPORTED_EXT, _file_mtime_iso


def collect_disk_files(approved_dir):
    found = []
    for gp_name in sorted(os.listdir(approved_dir)):
        gp_path = os.path.join(approved_dir, gp_name)
        if not os.path.isdir(gp_path):
            continue
        for p_name in sorted(os.listdir(gp_path)):
            p_path = os.path.join(gp_path, p_name)
            if not os.path.isdir(p_path):
                continue
            for fname in sorted(os.listdir(p_path)):
                full = os.path.join(p_path, fname)
                ext = os.path.splitext(fname)[1].lower()
                if ext in SUPPORTED_EXT and os.path.isfile(full):
                    found.append({
                        'approved_path': '/'.join([gp_name, p_name, fname]),
                        'filename': fname,
                        'full_path': full,
                    })
    return found


def load_scheduler_records(scheduler_db):
    """approved_path (normalized to '/') -> latest approved app_file_status row."""
    if not os.path.isfile(scheduler_db):
        return {}
    conn = sqlite3.connect(scheduler_db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT folder, filename, approved_path, file_mtime, created_at "
            "FROM app_file_status WHERE status='approved' AND approved_path IS NOT NULL "
            "ORDER BY created_at ASC"
        ).fetchall()
    finally:
        conn.close()
    records = {}
    for r in rows:
        # legacy paths were built with os.path.join: '\\' on Windows installs
        key = r['approved_path'].replace('\\', '/')
        records[key] = r  # ASC order: latest approval wins
    return records


def build_plan(approved_dir, scheduler_db):
    disk_files = collect_disk_files(approved_dir)
    records = load_scheduler_records(scheduler_db)

    plan = []
    for f in disk_files:
        rec = records.get(f['approved_path'])
        if rec is not None:
            plan.append({
                **f,
                'folder': rec['folder'],
                'file_mtime': rec['file_mtime'],
                'created_at': rec['created_at'],
                'approved_by': 'migration',
            })
        else:
            mtime = _file_mtime_iso(f['full_path'])
            plan.append({
                **f,
                'folder': '',
                'file_mtime': mtime,
                'created_at': mtime,
                'approved_by': 'migration-orphan',
            })

    # deterministic chain order: oldest approval first
    plan.sort(key=lambda p: ((p['created_at'] or ''), p['approved_path']))

    matched_paths = {p['approved_path'] for p in plan}
    missing = sorted(path for path in records if path not in matched_paths)
    return plan, missing


def run_migration(plan):
    with ledger.ledger_connect() as conn:
        for item in plan:
            with open(item['full_path'], 'rb') as fh:
                content = fh.read()
            ledger.append_entry(
                conn, item['folder'], item['filename'], item['approved_path'],
                content, file_mtime=item['file_mtime'],
                approved_by=item['approved_by'], created_at=item['created_at'],
            )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--approved-dir', default='approved')
    parser.add_argument('--scheduler-db', default='scheduler.db')
    parser.add_argument('--approvals-db', default='approvals.db')
    parser.add_argument('--dry-run', action='store_true', help='print the plan, write nothing')
    parser.add_argument('--append', action='store_true',
                        help='allow ingesting into a ledger that already has entries')
    parser.add_argument('--verify-only', action='store_true',
                        help='verify the existing ledger chain and blobs, then exit')
    args = parser.parse_args(argv)

    ledger.APPROVALS_DB = args.approvals_db
    ledger.init_ledger_db()

    if args.verify_only:
        with ledger.ledger_connect() as conn:
            result = ledger.verify_chain(conn)
        print(f"entries: {result['entries']}  blobs: {result['blobs']}")
        for err in result['errors']:
            print('ERROR:', err)
        print('chain OK' if result['ok'] else 'chain FAILED')
        return 0 if result['ok'] else 1

    if not os.path.isdir(args.approved_dir):
        print(f"approved dir not found: {args.approved_dir}")
        return 1

    with ledger.ledger_connect() as conn:
        existing = conn.execute('SELECT COUNT(*) FROM approval_ledger').fetchone()[0]
    if existing and not args.append:
        print(f"ledger already has {existing} entries - refusing to run (use --append to override)")
        return 1

    plan, missing = build_plan(args.approved_dir, args.scheduler_db)

    print(f"{'DRY RUN - ' if args.dry_run else ''}{len(plan)} file(s) to ingest:")
    for item in plan:
        src = item['folder'] or '(orphan: source folder unknown)'
        print(f"  {item['approved_path']}  <- {src}  [{item['created_at']}]")
    for path in missing:
        print(f"  WARNING: approval record exists but copy is missing on disk: {path}")

    if args.dry_run:
        return 0

    run_migration(plan)

    with ledger.ledger_connect() as conn:
        result = ledger.verify_chain(conn)
    print(f"ingested {len(plan)} entries; chain verification: "
          f"{'OK' if result['ok'] else 'FAILED'} "
          f"({result['entries']} entries, {result['blobs']} blobs)")
    for err in result['errors']:
        print('ERROR:', err)
    if result['ok']:
        print("The approved/ folder was NOT deleted. Verify the app, then remove it manually.")
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
