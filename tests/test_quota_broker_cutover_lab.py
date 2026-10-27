"""Offline synthetic SQLite replacement and rollback; never a real migration."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from facekids.quota_broker_cutover_lab import rehearse_offline_cutover
from facekids.storage import Storage


class OfflineQuotaCutoverTests(unittest.TestCase):
    def fixture(self, parent: Path) -> Path:
        root = parent / "facekids-quota-lab"
        root.mkdir()
        db = root / "fixture.sqlite3"
        store = Storage(db)
        first = store.add_person("Child A", 30)
        second = store.add_person("Child B", 45)
        store.charge(first, 35, "2026-10-24")
        store.charge(second, 77.5, "2026-10-24")
        store.close()
        return db

    def test_rehearsal_restores_original_exactly(self):
        with TemporaryDirectory() as td:
            db = self.fixture(Path(td))
            before = hashlib.sha256(db.read_bytes()).hexdigest()
            receipt = rehearse_offline_cutover(db, lab_root=db.parent)
            self.assertTrue(receipt.preview_verified)
            self.assertEqual(receipt.profiles, 2)
            self.assertEqual(receipt.quota_rows, 2)
            self.assertEqual(receipt.original_sha256, before)
            self.assertEqual(receipt.restored_sha256, before)
            self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)
            self.assertTrue(receipt.backup.exists())
            with closing(sqlite3.connect(receipt.backup)) as backup:
                self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(
                    backup.execute("SELECT SUM(seconds) FROM daily_usage").fetchone()[0],
                    112.5,
                )
            self.assertEqual(list(db.parent.glob(".facekids-held-*")), [])
            self.assertEqual(list(db.parent.glob(".facekids-retired-*")), [])
            self.assertEqual(list(db.parent.glob(".facekids-stage-*")), [])

    def test_fault_after_cutover_still_restores_original_bytes(self):
        with TemporaryDirectory() as td:
            db = self.fixture(Path(td))
            original = db.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "Synthetic failure"):
                rehearse_offline_cutover(db, lab_root=db.parent, inject_failure=True)
            self.assertEqual(db.read_bytes(), original)
            self.assertEqual(list(db.parent.glob(".facekids-held-*")), [])
            self.assertEqual(list(db.parent.glob(".facekids-retired-*")), [])
            self.assertEqual(list(db.parent.glob(".facekids-stage-*")), [])

    def test_reject_wal_and_unsafe_nonlab_directories(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            db = self.fixture(base)
            before = db.read_bytes()
            wal = Path(str(db) + "-wal")
            wal.write_bytes(b"deliberately unsafe checkpoint")
            with self.assertRaisesRegex(ValueError, "checkpointed"):
                rehearse_offline_cutover(db, lab_root=db.parent)
            wal.unlink()
            outside = base / "legacy.sqlite3"
            outside.write_bytes(before)
            with self.assertRaises(ValueError):
                rehearse_offline_cutover(outside, lab_root=base)
            production = base / "ProgramData" / "FaceKids"
            production.mkdir(parents=True)
            lab = production / "facekids-quota-lab"
            lab.mkdir()
            forbidden = lab / "fixture.sqlite3"
            forbidden.write_bytes(before)
            with patch.dict(os.environ, {"PROGRAMDATA": str(base / "ProgramData")}):
                with self.assertRaisesRegex(ValueError, "Production"):
                    rehearse_offline_cutover(forbidden, lab_root=lab)
            self.assertEqual(db.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
