"""Synthetic WAL cutover and rollback; no production files or Windows ACLs."""
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from facekids.quota_migration_lab import prepare_lab_cutover, restore_lab_snapshot
from facekids.storage import Storage


class LabCutoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name) / "facekids-quota-lab"
        self.legacy = self.root / "legacy"
        self.secure = self.root / "protected"
        self.backups = self.root / "backups"
        for path in (self.legacy, self.secure, self.backups):
            path.mkdir(parents=True)
        self.source = self.legacy / "criancas.sqlite3"
        self.dest = self.secure / "criancas.sqlite3"
        self.snap = self.backups / "baseline.sqlite3"
        store = Storage(self.source)
        try:
            self.people = [store.add_person("Synthetic " + str(i), 2) for i in range(3)]
            store.db.execute("PRAGMA journal_mode=WAL")
            for i, person in enumerate(self.people):
                store.charge(person, (i + 1) * 7, "2026-10-24")
        finally:
            store.close()

    def tearDown(self):
        self.tmp.cleanup()

    def balances(self, database: Path):
        store = Storage(database)
        try:
            return [store.used(person, "2026-10-24") for person in self.people]
        finally:
            store.close()

    def test_wal_snapshot_and_cutover_to_new_protected_directory(self):
        prepare_lab_cutover(self.root, self.source, self.dest, self.snap)
        self.assertEqual(self.balances(self.dest), [7, 14, 21])
        self.assertEqual(self.balances(self.snap), [7, 14, 21])
        self.assertEqual(self.balances(self.source), [7, 14, 21])
        modified = Storage(self.dest)
        try:
            modified.charge(self.people[0], 8, "2026-10-24")
        finally:
            modified.close()
        self.assertEqual(self.balances(self.dest), [15, 14, 21])
        restore_lab_snapshot(self.root, self.dest, self.snap)
        self.assertEqual(self.balances(self.dest), [7, 14, 21])
        self.assertEqual(self.balances(self.source), [7, 14, 21])

    def test_failure_does_not_promote_and_leaves_usable_backup(self):
        with self.assertRaisesRegex(RuntimeError, "Injected cutover failure"):
            prepare_lab_cutover(
                self.root, self.source, self.dest, self.snap, inject_failure=True
            )
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.balances(self.snap), [7, 14, 21])
        self.assertEqual(self.balances(self.source), [7, 14, 21])
        restore_lab_snapshot(self.root, self.dest, self.snap)
        self.assertEqual(self.balances(self.dest), [7, 14, 21])

    def test_refuse_outside_lab_and_preexisting_target(self):
        bad_root = Path(self.tmp.name) / "not-authorized"
        with self.assertRaises(ValueError):
            prepare_lab_cutover(bad_root, self.source, self.dest, self.snap)
        self.dest.write_bytes(b"existing do not overwrite")
        with self.assertRaises(ValueError):
            prepare_lab_cutover(self.root, self.source, self.dest, self.snap)
        self.assertEqual(self.dest.read_bytes(), b"existing do not overwrite")


if __name__ == "__main__":
    unittest.main()
