"""Regression tests: cutover must reject equal-count mutations and schema drift."""
import sqlite3
import unittest
from facekids.quota_vm_snapshot_guard import assert_snapshot_matches


class VmSnapshotGuardTests(unittest.TestCase):
    def setUp(self):
        self.live = sqlite3.connect(":memory:")
        self.snapshot = sqlite3.connect(":memory:")
        for db in (self.live, self.snapshot):
            db.execute("CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT)")
            db.execute("CREATE TABLE daily_usage (person_id INT, seconds REAL)")
            db.execute("CREATE TABLE quota_tick_receipts (event_id TEXT, charged REAL)")
            db.execute("INSERT INTO people VALUES (1, 'Synthetic')")
            db.execute("INSERT INTO daily_usage VALUES (1, 12.0)")
            db.execute("INSERT INTO quota_tick_receipts VALUES ('evt', 3.0)")
            db.commit()

    def tearDown(self):
        self.live.close()
        self.snapshot.close()

    def test_identical_snapshot_is_accepted(self):
        self.live.execute("BEGIN IMMEDIATE")
        assert_snapshot_matches(self.live, self.snapshot)
        self.live.rollback()

    def test_changed_balance_same_row_count_rejected(self):
        self.live.execute("UPDATE daily_usage SET seconds=17 WHERE person_id=1")
        self.live.commit()
        self.live.execute("BEGIN IMMEDIATE")
        with self.assertRaisesRegex(RuntimeError, "content changed"):
            assert_snapshot_matches(self.live, self.snapshot)
        self.live.rollback()

    def test_changed_receipt_same_row_count_rejected(self):
        self.live.execute("UPDATE quota_tick_receipts SET charged=8")
        self.live.commit()
        self.live.execute("BEGIN IMMEDIATE")
        with self.assertRaisesRegex(RuntimeError, "content changed"):
            assert_snapshot_matches(self.live, self.snapshot)
        self.live.rollback()

    def test_changed_schema_rejected(self):
        self.live.execute("ALTER TABLE people ADD COLUMN external_id TEXT")
        self.live.commit()
        self.live.execute("BEGIN IMMEDIATE")
        with self.assertRaisesRegex(RuntimeError, "schema changed"):
            assert_snapshot_matches(self.live, self.snapshot)
        self.live.rollback()

    def test_changed_person_without_row_count_rejected(self):
        self.live.execute("UPDATE people SET name='Other' WHERE id=1")
        self.live.commit()
        self.live.execute("BEGIN IMMEDIATE")
        with self.assertRaisesRegex(RuntimeError, "content changed"):
            assert_snapshot_matches(self.live, self.snapshot)
        self.live.rollback()

    def test_duplicate_rows_with_same_count_rejected(self):
        self.live.execute("INSERT INTO daily_usage VALUES (1, 9)")
        self.live.execute("DELETE FROM daily_usage WHERE seconds=12")
        self.live.commit()
        self.live.execute("BEGIN IMMEDIATE")
        with self.assertRaisesRegex(RuntimeError, "content changed"):
            assert_snapshot_matches(self.live, self.snapshot)
        self.live.rollback()


if __name__ == "__main__":
    unittest.main()
