from contextlib import closing
"""Snapshot migration rehearsals only (no real Windows installation)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from facekids.quota_broker_migration import create_vm_snapshot
from facekids.storage import Storage


class MigrationSnapshotTests(unittest.TestCase):
    def test_backup_preserves_wal_and_all_profiles_without_mutating_source(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            db_file = root / "source.sqlite3"
            storage = Storage(db_file)
            try:
                first = storage.add_person("First", 30)
                second = storage.add_person("Second", 45)
                storage.charge(first, 12.5, "2026-10-24")
                storage.add_bonus(second, 15, "2026-10-24")
                result = create_vm_snapshot(db_file, root / "copy.sqlite3", lab_root=root)
                self.assertEqual(result.children, 2)
                self.assertEqual(result.ledger_rows, 1)
                self.assertEqual(len(result.sha256), 64)
                with closing(sqlite3.connect(result.output)) as snapshot:
                    self.assertEqual(snapshot.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(snapshot.execute("SELECT COUNT(*) FROM people").fetchone()[0], 2)
                    self.assertEqual(snapshot.execute("SELECT seconds FROM daily_usage").fetchone()[0], 12.5)
                    self.assertEqual(snapshot.execute("SELECT seconds FROM daily_bonus").fetchone()[0], 900)
                self.assertEqual(storage.remaining(first, "2026-10-24"), 1800 - 12.5)
            finally:
                storage.close()

    def test_fail_closed_on_overwrite_missing_and_path_traversal(self):
        with TemporaryDirectory() as td, TemporaryDirectory() as outside:
            root = Path(td)
            source = root / "source.sqlite3"
            store = Storage(source)
            store.add_person("Child", 10)
            store.close()
            target = root / "backup.sqlite3"
            create_vm_snapshot(source, target, lab_root=root)
            for src, dst in (
                (source, target),
                (source, source),
                (Path(outside) / "unknown.sqlite3", root / "other.sqlite3"),
                (source, Path(outside) / "copy.sqlite3"),
            ):
                with self.subTest(source=str(src), target=str(dst)):
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        create_vm_snapshot(src, dst, lab_root=root)
            self.assertEqual(len(list(root.glob("*.facekids-incomplete"))), 0)

    def test_restore_in_disposable_lab_keeps_original_ledger_independent(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            original = root / "original.sqlite3"
            source = Storage(original)
            cid = source.add_person("Child", 10)
            day = "2026-10-24"
            source.charge(cid, 60, day)
            snapshot = create_vm_snapshot(original, root / "backup.sqlite3", lab_root=root)
            # The original is deliberately changed after the backup.
            source.charge(cid, 120, day)
            self.assertEqual(source.used(cid, day), 180)
            source.close()
            restored = create_vm_snapshot(
                snapshot.output, root / "restored.sqlite3", lab_root=root
            )
            with closing(sqlite3.connect(restored.output)) as check:
                usage = check.execute(
                    "SELECT seconds FROM daily_usage WHERE person_id=? AND day=?",
                    (cid, day),
                ).fetchone()[0]
                self.assertEqual(usage, 60)
            with closing(sqlite3.connect(original)) as current:
                self.assertEqual(
                    current.execute("SELECT seconds FROM daily_usage").fetchone()[0],
                    180,
                )
            self.assertEqual(restored.children, 1)
            self.assertEqual(restored.ledger_rows, 1)

    def test_does_not_replace_corrupt_database(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            invalid = root / "invalid.sqlite3"
            invalid.write_bytes(b"not a database")
            with self.assertRaises(sqlite3.DatabaseError):
                create_vm_snapshot(invalid, root / "backup.sqlite3", lab_root=root)
            self.assertFalse((root / "backup.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
