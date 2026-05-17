import json
import os
import sys
import sqlite3
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import db as db_module
from recurrence import (
    detach_recurring_entries,
    ensure_range_materialized,
    generate_entries,
    is_last_week_of_month,
    matches,
    materialize_task,
    needs_daily_check,
    parse_recurrence,
    valid_range,
)


class MatchesTests(unittest.TestCase):
    def test_daily(self):
        self.assertTrue(matches({'type': 'daily'}, date(2026, 5, 17)))

    def test_weekday_excludes_weekend(self):
        rec = {'type': 'weekday'}
        self.assertTrue(matches(rec, date(2026, 5, 18)))   # Mon
        self.assertTrue(matches(rec, date(2026, 5, 22)))   # Fri
        self.assertFalse(matches(rec, date(2026, 5, 17)))  # Sun
        self.assertFalse(matches(rec, date(2026, 5, 23)))  # Sat

    def test_weekly_specific_days(self):
        rec = {'type': 'weekly', 'daysOfWeek': [1, 3]}  # Mon, Wed
        self.assertTrue(matches(rec, date(2026, 5, 18)))
        self.assertTrue(matches(rec, date(2026, 5, 20)))
        self.assertFalse(matches(rec, date(2026, 5, 19)))

    def test_monthly_day_of_month(self):
        rec = {'type': 'monthly', 'monthlyMode': 'day', 'dayOfMonth': 15}
        self.assertTrue(matches(rec, date(2026, 5, 15)))
        self.assertFalse(matches(rec, date(2026, 5, 14)))

    def test_monthly_nth_weekday(self):
        # 2nd Tuesday of May 2026 -> May 12 (Tuesdays: 5, 12, 19, 26)
        rec = {'type': 'monthly', 'monthlyMode': 'weekday', 'nth': 2, 'nthWeekday': 2}
        self.assertTrue(matches(rec, date(2026, 5, 12)))
        self.assertFalse(matches(rec, date(2026, 5, 5)))
        self.assertFalse(matches(rec, date(2026, 5, 19)))

    def test_monthly_last_weekday(self):
        # Last Friday of May 2026 -> May 29 (Fridays: 1, 8, 15, 22, 29)
        rec = {'type': 'monthly', 'monthlyMode': 'weekday', 'nth': -1, 'nthWeekday': 5}
        self.assertTrue(matches(rec, date(2026, 5, 29)))
        self.assertFalse(matches(rec, date(2026, 5, 22)))

    def test_custom_every_n_days(self):
        rec = {'type': 'custom', 'unit': 'days', 'interval': 3, 'startDate': '2026-05-17'}
        self.assertTrue(matches(rec, date(2026, 5, 17)))
        self.assertFalse(matches(rec, date(2026, 5, 18)))
        self.assertFalse(matches(rec, date(2026, 5, 19)))
        self.assertTrue(matches(rec, date(2026, 5, 20)))

    def test_custom_weeks_with_days_of_week(self):
        # Every 2 weeks on Tuesday, starting Tue 2026-05-19
        rec = {
            'type': 'custom', 'unit': 'weeks', 'interval': 2,
            'daysOfWeek': [2], 'startDate': '2026-05-19'
        }
        self.assertTrue(matches(rec, date(2026, 5, 19)))
        self.assertFalse(matches(rec, date(2026, 5, 26)))  # week 1, skip
        self.assertTrue(matches(rec, date(2026, 6, 2)))    # week 2
        self.assertFalse(matches(rec, date(2026, 5, 20)))  # Wed, wrong dow

    def test_custom_months_day_of_month(self):
        rec = {
            'type': 'custom', 'unit': 'months', 'interval': 2,
            'monthlyMode': 'day', 'dayOfMonth': 15, 'startDate': '2026-05-15'
        }
        self.assertTrue(matches(rec, date(2026, 5, 15)))
        self.assertFalse(matches(rec, date(2026, 6, 15)))  # 1 month later, skip
        self.assertTrue(matches(rec, date(2026, 7, 15)))   # 2 months later

    def test_custom_months_nth_weekday(self):
        # Every 2 months on the 2nd Tuesday
        rec = {
            'type': 'custom', 'unit': 'months', 'interval': 2,
            'monthlyMode': 'weekday', 'nth': 2, 'nthWeekday': 2,
            'startDate': '2026-05-01'
        }
        self.assertTrue(matches(rec, date(2026, 5, 12)))   # 2nd Tue of May
        self.assertFalse(matches(rec, date(2026, 6, 9)))   # June would be 1 month later
        self.assertTrue(matches(rec, date(2026, 7, 14)))   # 2nd Tue of July

    def test_before_start_date_is_no_match(self):
        rec = {'type': 'custom', 'unit': 'days', 'interval': 1, 'startDate': '2026-05-17'}
        self.assertFalse(matches(rec, date(2026, 5, 16)))

    def test_none_rule_never_matches(self):
        self.assertFalse(matches(None, date(2026, 5, 17)))
        self.assertFalse(matches({}, date(2026, 5, 17)))


class GenerateEntriesTests(unittest.TestCase):
    def test_daily_slot_key_and_duration(self):
        rec = {'type': 'daily', 'time': '09:30', 'duration': 60}
        entries = list(generate_entries(rec, date(2026, 5, 17), date(2026, 5, 19)))
        self.assertEqual(entries, [
            ('2026-05-17-9-2', 4),
            ('2026-05-18-9-2', 4),
            ('2026-05-19-9-2', 4),
        ])

    def test_duration_clamped_to_min(self):
        rec = {'type': 'daily', 'time': '09:00', 'duration': 5}
        slot, dur = next(generate_entries(rec, date(2026, 5, 17), date(2026, 5, 17)))
        self.assertEqual(dur, 1)  # 15 min minimum quantized to 1 quarter

    def test_time_default_when_missing(self):
        rec = {'type': 'daily', 'duration': 60}
        slot, dur = next(generate_entries(rec, date(2026, 5, 17), date(2026, 5, 17)))
        self.assertEqual(slot, '2026-05-17-9-0')


class RangeTests(unittest.TestCase):
    def test_valid_range_middle_of_month(self):
        s, e = valid_range(date(2026, 5, 17))
        self.assertEqual(s, date(2026, 4, 1))
        self.assertEqual(e, date(2026, 6, 30))

    def test_valid_range_last_week_extends(self):
        s, e = valid_range(date(2026, 5, 26))
        self.assertEqual(s, date(2026, 4, 1))
        self.assertEqual(e, date(2026, 7, 31))

    def test_valid_range_january(self):
        s, e = valid_range(date(2026, 1, 15))
        self.assertEqual(s, date(2025, 12, 1))
        self.assertEqual(e, date(2026, 2, 28))

    def test_valid_range_december(self):
        s, e = valid_range(date(2026, 12, 15))
        self.assertEqual(s, date(2026, 11, 1))
        self.assertEqual(e, date(2027, 1, 31))

    def test_valid_range_december_last_week(self):
        s, e = valid_range(date(2026, 12, 28))
        self.assertEqual(s, date(2026, 11, 1))
        self.assertEqual(e, date(2027, 2, 28))

    def test_is_last_week_threshold(self):
        # May 2026 has 31 days. Day 25 -> 6 days left, IS last week. Day 24 -> 7 days, is NOT.
        self.assertFalse(is_last_week_of_month(date(2026, 5, 24)))
        self.assertTrue(is_last_week_of_month(date(2026, 5, 25)))
        self.assertTrue(is_last_week_of_month(date(2026, 5, 31)))


class ParseRecurrenceTests(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(parse_recurrence(None))

    def test_dict_passthrough(self):
        self.assertEqual(parse_recurrence({'type': 'daily'}), {'type': 'daily'})

    def test_json_string(self):
        self.assertEqual(parse_recurrence('{"type":"daily"}'), {'type': 'daily'})

    def test_invalid_string(self):
        self.assertIsNone(parse_recurrence('not json'))


class _DbTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.tmp.close()
        self._orig_db = db_module.DB
        db_module.DB = self.tmp.name
        db_module.init_db()
        self.conn = sqlite3.connect(self.tmp.name)
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()
        db_module.DB = self._orig_db
        os.unlink(self.tmp.name)

    def _insert_task(self, task_id, recurrence=None):
        self.conn.execute(
            'INSERT INTO tasks (id, name, description, tags, color, code, input, recurrence) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (task_id, 'T', '', '', '#3b82f6', '', '',
             json.dumps(recurrence) if recurrence else None)
        )
        self.conn.commit()


class MaterializeTaskTests(_DbTestBase):
    def test_inserts_recurring_rows(self):
        self._insert_task('t1')
        rec = {'type': 'weekly', 'daysOfWeek': [1], 'time': '09:00',
               'duration': 60, 'startDate': '2026-05-04'}
        materialize_task(self.conn, 't1', rec, date(2026, 5, 1), date(2026, 5, 31))
        self.conn.commit()
        rows = self.conn.execute(
            'SELECT slot, is_recurring FROM schedule WHERE task_id=? ORDER BY slot',
            ('t1',)
        ).fetchall()
        # Mondays in May 2026: 4, 11, 18, 25
        self.assertEqual([r['slot'] for r in rows], [
            '2026-05-04-9-0', '2026-05-11-9-0', '2026-05-18-9-0', '2026-05-25-9-0',
        ])
        self.assertTrue(all(r['is_recurring'] == 1 for r in rows))

    def test_adopts_existing_individual_entry(self):
        # Pre-existing individual entry at a slot that the rule will hit
        self._insert_task('t1')
        cur = self.conn.execute(
            'INSERT INTO schedule (slot, task_id, duration, is_recurring) VALUES (?,?,?,0)',
            ('2026-05-18-9-0', 't1', 4)
        )
        existing_id = cur.lastrowid
        self.conn.commit()

        rec = {'type': 'weekly', 'daysOfWeek': [1], 'time': '09:00',
               'duration': 60, 'startDate': '2026-05-04'}
        materialize_task(self.conn, 't1', rec, date(2026, 5, 1), date(2026, 5, 31))
        self.conn.commit()

        # Same id should still exist, now flagged recurring (not deleted+recreated)
        row = self.conn.execute(
            'SELECT id, is_recurring FROM schedule WHERE slot=? AND task_id=?',
            ('2026-05-18-9-0', 't1')
        ).fetchone()
        self.assertEqual(row['id'], existing_id)
        self.assertEqual(row['is_recurring'], 1)

        # No duplicate at that slot
        count = self.conn.execute(
            'SELECT COUNT(*) FROM schedule WHERE slot=? AND task_id=?',
            ('2026-05-18-9-0', 't1')
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_preserves_per_chip_input_on_rematerialize(self):
        # Same rule re-saved — per-chip inputs at matching slots survive
        self._insert_task('t1')
        rec = {'type': 'weekly', 'daysOfWeek': [1], 'time': '09:00',
               'duration': 60, 'startDate': '2026-05-04'}
        materialize_task(self.conn, 't1', rec, date(2026, 5, 1), date(2026, 5, 31))
        self.conn.execute(
            "UPDATE schedule SET input='custom-monday' WHERE task_id=? AND slot=?",
            ('t1', '2026-05-18-9-0')
        )
        self.conn.commit()

        materialize_task(self.conn, 't1', rec, date(2026, 5, 1), date(2026, 5, 31))
        self.conn.commit()

        row = self.conn.execute(
            'SELECT input, is_recurring FROM schedule WHERE task_id=? AND slot=?',
            ('t1', '2026-05-18-9-0')
        ).fetchone()
        self.assertEqual(row['input'], 'custom-monday')
        self.assertEqual(row['is_recurring'], 1)

    def test_drops_per_chip_input_when_slot_no_longer_materialized(self):
        # Rule changes from Mon to Tue — old Monday inputs are gone (slot key shifted)
        self._insert_task('t1')
        rec_old = {'type': 'weekly', 'daysOfWeek': [1], 'time': '09:00',
                   'duration': 60, 'startDate': '2026-05-04'}
        materialize_task(self.conn, 't1', rec_old, date(2026, 5, 1), date(2026, 5, 31))
        self.conn.execute(
            "UPDATE schedule SET input='custom-monday' WHERE task_id=? AND slot=?",
            ('t1', '2026-05-18-9-0')
        )
        self.conn.commit()

        rec_new = {'type': 'weekly', 'daysOfWeek': [2], 'time': '09:00',
                   'duration': 60, 'startDate': '2026-05-04'}
        materialize_task(self.conn, 't1', rec_new, date(2026, 5, 1), date(2026, 5, 31))
        self.conn.commit()

        # No row at the old Monday slot
        row = self.conn.execute(
            'SELECT input FROM schedule WHERE task_id=? AND slot=?',
            ('t1', '2026-05-18-9-0')
        ).fetchone()
        self.assertIsNone(row)
        # New Tuesday slots have NULL input (no carryover)
        rows = self.conn.execute(
            'SELECT input FROM schedule WHERE task_id=? AND is_recurring=1', ('t1',)
        ).fetchall()
        self.assertTrue(all(r['input'] is None for r in rows))

    def test_adopt_keeps_individual_input(self):
        self._insert_task('t1')
        self.conn.execute(
            'INSERT INTO schedule (slot, task_id, duration, is_recurring, input) '
            'VALUES (?,?,?,0,?)',
            ('2026-05-18-9-0', 't1', 4, 'individual-input')
        )
        self.conn.commit()

        rec = {'type': 'weekly', 'daysOfWeek': [1], 'time': '09:00',
               'duration': 60, 'startDate': '2026-05-04'}
        materialize_task(self.conn, 't1', rec, date(2026, 5, 1), date(2026, 5, 31))
        self.conn.commit()

        row = self.conn.execute(
            'SELECT input, is_recurring FROM schedule WHERE task_id=? AND slot=?',
            ('t1', '2026-05-18-9-0')
        ).fetchone()
        self.assertEqual(row['input'], 'individual-input')
        self.assertEqual(row['is_recurring'], 1)

    def test_rewrite_wipes_old_recurring_in_range(self):
        # Old rule materialized; new rule should replace within range, not append
        self._insert_task('t1')
        rec_old = {'type': 'weekly', 'daysOfWeek': [1], 'time': '09:00',
                   'duration': 60, 'startDate': '2026-05-04'}
        materialize_task(self.conn, 't1', rec_old, date(2026, 5, 1), date(2026, 5, 31))
        rec_new = {'type': 'weekly', 'daysOfWeek': [3], 'time': '14:00',
                   'duration': 30, 'startDate': '2026-05-04'}
        materialize_task(self.conn, 't1', rec_new, date(2026, 5, 1), date(2026, 5, 31))
        self.conn.commit()
        slots = [r['slot'] for r in self.conn.execute(
            'SELECT slot FROM schedule WHERE task_id=? ORDER BY slot', ('t1',)
        ).fetchall()]
        # Wednesdays in May 2026: 6, 13, 20, 27 — all at 14:00 = slot ...-14-0
        self.assertEqual(slots, [
            '2026-05-06-14-0', '2026-05-13-14-0',
            '2026-05-20-14-0', '2026-05-27-14-0',
        ])


class DetachTests(_DbTestBase):
    def test_detach_flips_flag_keeps_rows(self):
        self._insert_task('t1')
        rec = {'type': 'daily', 'time': '09:00', 'duration': 60, 'startDate': '2026-05-17'}
        materialize_task(self.conn, 't1', rec, date(2026, 5, 17), date(2026, 5, 19))
        self.conn.commit()

        detach_recurring_entries(self.conn, 't1')
        self.conn.commit()

        rows = self.conn.execute(
            'SELECT is_recurring FROM schedule WHERE task_id=?', ('t1',)
        ).fetchall()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r['is_recurring'] == 0 for r in rows))


class EnsureRangeMaterializedTests(_DbTestBase):
    def test_first_call_materializes(self):
        self._insert_task('t1', recurrence={
            'type': 'weekly', 'daysOfWeek': [1], 'time': '09:00',
            'duration': 60, 'startDate': '2026-05-04'
        })
        self.assertTrue(needs_daily_check(self.conn, date(2026, 5, 17)))
        _, _, did = ensure_range_materialized(self.conn, date(2026, 5, 17))
        self.conn.commit()
        self.assertTrue(did)
        count = self.conn.execute('SELECT COUNT(*) FROM schedule').fetchone()[0]
        self.assertGreater(count, 0)

    def test_second_call_same_day_is_noop_for_work(self):
        self._insert_task('t1', recurrence={
            'type': 'daily', 'time': '09:00', 'duration': 60, 'startDate': '2026-05-17'
        })
        ensure_range_materialized(self.conn, date(2026, 5, 17))
        self.conn.commit()
        self.assertFalse(needs_daily_check(self.conn, date(2026, 5, 17)))
        _, _, did = ensure_range_materialized(self.conn, date(2026, 5, 17))
        self.assertFalse(did)


if __name__ == '__main__':
    unittest.main()
