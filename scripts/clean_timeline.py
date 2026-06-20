"""Clean Timeline data records from scheduler.db (R&D / testing helper).

Scope: this clears ONLY the Timeline feature's five tables:
  - assignments         (reusable project chips in the sidebar)
  - timeline_schedule   (assignment chips dropped onto week-grid days)
  - timeline_sessions   (recorded strip sessions)
  - timeline_marks      (lap marks within a session)
  - timeline_segments   (spans between marks)

It NEVER touches any other feature's data:
  - tasks / schedule data (the Scheduler view)   -> table `tasks`
  - the Events view                              -> table `events`
  - the Applications view                        -> table `app_file_status`
  - users / auth                                 -> table `users`

By default it wipes all five Timeline tables. Flags narrow that down.

Usage:
    python3 scripts/clean_timeline.py --dry-run              # show counts, delete nothing
    python3 scripts/clean_timeline.py                        # wipe all Timeline data (prompts)
    python3 scripts/clean_timeline.py --yes                  # ...without the prompt
    python3 scripts/clean_timeline.py --keep-assignments     # wipe recordings + week-grid, keep assignment definitions
    python3 scripts/clean_timeline.py --date 2026-06-08      # only that day's sessions + week-grid chips (keeps assignments)
    python3 scripts/clean_timeline.py --db /tmp/test.db      # target a different sqlite file

Safety:
  - Always supports --dry-run. A real run prints a plan and asks for confirmation
    unless --yes. Runs inside one transaction (all-or-nothing).
  - Never deletes the database file, only rows in the Timeline tables above.
"""

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import db

# The only tables this script is ever allowed to touch.
TIMELINE_TABLES = (
    'assignments',
    'timeline_schedule',
    'timeline_sessions',
    'timeline_marks',
    'timeline_segments',
)


def table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def session_ids_in_scope(conn, date):
    if not table_exists(conn, 'timeline_sessions'):
        return []
    if date:
        rows = conn.execute(
            'SELECT id FROM timeline_sessions WHERE session_date=?', (date,)
        ).fetchall()
    else:
        rows = conn.execute('SELECT id FROM timeline_sessions').fetchall()
    return [r[0] for r in rows]


def main():
    ap = argparse.ArgumentParser(
        description='Clean ONLY Timeline data from scheduler.db (R&D / testing). '
                    'Never touches Scheduler, Events, or Applications data.'
    )
    ap.add_argument('--dry-run', action='store_true',
                    help='show what would be deleted, then exit without deleting')
    ap.add_argument('--date', metavar='YYYY-MM-DD',
                    help='restrict to one date: that day\'s sessions and week-grid '
                         'chips only (assignment definitions are kept)')
    ap.add_argument('--keep-assignments', action='store_true',
                    help='keep assignment definitions; wipe recordings and week-grid chips')
    ap.add_argument('--yes', action='store_true', help='skip the confirmation prompt')
    ap.add_argument('--db', metavar='PATH',
                    help='sqlite file to operate on (default: %s)' % db.DB)
    args = ap.parse_args()

    if args.db:
        db.DB = args.db

    if not os.path.isfile(db.DB):
        ap.error('database not found: %s' % db.DB)

    if args.date:
        try:
            datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            ap.error('--date must be in YYYY-MM-DD form')

    # Assignments are global (not date-scoped), so a dated run can't target them.
    clear_assignments = not args.keep_assignments and not args.date

    with db.db_connect() as conn:
        sess_ids = session_ids_in_scope(conn, args.date)
        placeholders = ','.join('?' * len(sess_ids))

        if sess_ids:
            n_marks = conn.execute(
                'SELECT COUNT(*) FROM timeline_marks WHERE session_id IN (%s)' % placeholders,
                sess_ids).fetchone()[0]
            n_segments = conn.execute(
                'SELECT COUNT(*) FROM timeline_segments WHERE session_id IN (%s)' % placeholders,
                sess_ids).fetchone()[0]
        else:
            n_marks = n_segments = 0
        n_sessions = len(sess_ids)

        if table_exists(conn, 'timeline_schedule'):
            if args.date:
                n_schedule = conn.execute(
                    'SELECT COUNT(*) FROM timeline_schedule WHERE slot=?', (args.date,)
                ).fetchone()[0]
            else:
                n_schedule = conn.execute('SELECT COUNT(*) FROM timeline_schedule').fetchone()[0]
        else:
            n_schedule = 0

        n_assignments = (conn.execute('SELECT COUNT(*) FROM assignments').fetchone()[0]
                         if clear_assignments and table_exists(conn, 'assignments') else 0)

        scope = ('date=%s' % args.date) if args.date else 'all dates'
        print('Timeline cleanup plan (%s) on %s:' % (scope, db.DB))
        print('  strip sessions : %d  (+ %d marks, %d segments)' % (n_sessions, n_marks, n_segments))
        print('  week-grid chips: %d' % n_schedule)
        print('  assignments    : %d%s' % (
            n_assignments, '' if clear_assignments else '   (kept)'))

        total = n_sessions + n_marks + n_segments + n_schedule + n_assignments
        if total == 0:
            print('Nothing to delete.')
            return

        if args.dry_run:
            print('Dry run: no rows deleted.')
            return

        if not args.yes:
            reply = input('Delete these Timeline rows? This cannot be undone. [y/N] ').strip().lower()
            if reply not in ('y', 'yes'):
                print('Aborted; nothing deleted.')
                return

        if sess_ids:
            conn.execute('DELETE FROM timeline_marks WHERE session_id IN (%s)' % placeholders, sess_ids)
            conn.execute('DELETE FROM timeline_segments WHERE session_id IN (%s)' % placeholders, sess_ids)
            conn.execute('DELETE FROM timeline_sessions WHERE id IN (%s)' % placeholders, sess_ids)
        if table_exists(conn, 'timeline_schedule'):
            if args.date:
                conn.execute('DELETE FROM timeline_schedule WHERE slot=?', (args.date,))
            else:
                conn.execute('DELETE FROM timeline_schedule')
        if clear_assignments and table_exists(conn, 'assignments'):
            # Drop dangling references from any segments that survived a scoped run.
            if table_exists(conn, 'timeline_segments'):
                conn.execute('UPDATE timeline_segments SET assignment_id=NULL')
            conn.execute('DELETE FROM assignments')

    print('Done. Deleted %d Timeline row(s).' % total)


if __name__ == '__main__':
    main()
