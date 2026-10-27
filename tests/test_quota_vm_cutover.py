"""VM-only cutover: one writer, transactional guard, rollback and restart."""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import numpy as np
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from facekids.quota_vm_cutover import (
    OWNER_KEY, SERVICE_ONLY, promote_vm_lab_writer, restore_vm_lab_offline
)
from facekids.quota_broker_writer_scm_win import LAB_MARKER_KEY, LAB_MARKER_VALUE
from facekids.storage import Storage
from facekids.quota_broker_migration import create_vm_snapshot


class OfflineVmCutoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="facekids-offline-vm-cutover-")
        self.root = Path(self.temp.name) / "facekids-quota-lab"
        self.root.mkdir()
        self.db = self.root / "writer-fixture.sqlite3"
        self.models = self.root / "models"
        self.models.mkdir()
        self.models.joinpath("synthetic-face.bin").write_bytes(b"synthetic")
        self.store = Storage(self.db)
        self.people = [self.store.add_person("Synthetic " + str(n), 3)
                       for n in range(1, 4)]
        self.store.set_setting(LAB_MARKER_KEY, LAB_MARKER_VALUE)
        self.day = "2026-10-25"
        self.store.charge(self.people[0], 3, self.day)
        self.store.add_bonus(self.people[2], 2, self.day)
        self.store.add_embedding(self.people[2], np.arange(32, dtype=np.float32))
        self.store.close()
        self.backup = self.root / "before-cutover.sqlite3"
        self.undo = self.root / "before-rollback.sqlite3"
        self.config = {
            "VmLabOnly": 1, "WriterEnabled": 1,
            "Database": str(self.db), "Models": str(self.models),
            "ChildSid": "S-1-5-21-10-20-30-1001",
            "ServiceSid": "S-1-5-18",
        }

    def tearDown(self):
        self.temp.cleanup()

    def promote(self):
        return promote_vm_lab_writer(
            self.config, backup_path=self.backup, offline_gate=lambda: True
        )

    def test_promote_without_damage_then_block_all_legacy_writers(self):
        result = self.promote()
        self.assertEqual(result.owner, SERVICE_ONLY)
        self.assertEqual(result.original_snapshot.children, 3)
        self.assertTrue(self.backup.exists())
        a = Storage(self.db)
        b = Storage(self.db)
        try:
            self.assertEqual(a.get_setting(OWNER_KEY), SERVICE_ONLY)
            for writer in (a, b):
                with self.assertRaises(PermissionError):
                    writer.charge(self.people[0], 999, self.day)
                with self.assertRaises(PermissionError):
                    writer.charge_up_to_available(self.people[1], 1, self.day)
            self.assertEqual(a.used(self.people[0], self.day), 3)
            self.assertEqual(a.used(self.people[1], self.day), 0)
            receipt = "a" * 32
            self.assertEqual(a.charge_capped_once(
                receipt, self.people[1], 7, self.day
            ), 7)
            self.assertEqual(b.charge_capped_once(
                receipt, self.people[1], 7, self.day
            ), 0, "Second service worker cannot replay the same tick")
            self.assertEqual(a.used(self.people[1], self.day), 7)
            self.assertEqual(b.used(self.people[2], self.day), 0)
        finally:
            a.close()
            b.close()

    def test_restore_after_service_stop_preserves_pre_restore_image(self):
        self.promote()
        with closing(Storage(self.db)) as service:
            service.charge_capped_once("b" * 32, self.people[1], 13, self.day)
        undo_path = restore_vm_lab_offline(
            self.config, backup_path=self.backup,
            preserved_current_path=self.undo, offline_gate=lambda: True
        )
        self.assertTrue(undo_path.samefile(self.undo))
        with closing(Storage(self.db)) as restored:
            self.assertIsNone(restored.get_setting(OWNER_KEY))
            self.assertEqual([restored.used(x, self.day) for x in self.people],
                             [3, 0, 0])
            self.assertEqual(restored.bonus(self.people[2], self.day), 120)
            self.assertEqual(restored.enrollment_count(self.people[2]), 1)
            vectors = restored.embeddings()
            self.assertEqual(vectors[0][0], self.people[2])
            np.testing.assert_array_equal(
                vectors[0][1], np.arange(32, dtype=np.float32)
            )
            restored.charge(self.people[0], 1, self.day)
            self.assertEqual(restored.used(self.people[0], self.day), 4)
        with closing(sqlite3.connect(self.undo)) as pre:
            self.assertEqual(pre.execute(
                "SELECT value FROM settings WHERE key=?", (OWNER_KEY,)
            ).fetchone(), (SERVICE_ONLY,))
            self.assertEqual(pre.execute(
                "SELECT seconds FROM daily_usage WHERE person_id=? AND day=?",
                (self.people[1], self.day)
            ).fetchone()[0], 13)

    def test_requires_verified_offline_state_and_never_overwrites_snapshots(self):
        with self.assertRaises(PermissionError):
            promote_vm_lab_writer(
                self.config, backup_path=self.backup, offline_gate=lambda: False
            )
        self.assertFalse(self.backup.exists())
        self.promote()
        with self.assertRaises(FileExistsError):
            self.promote()
        with self.assertRaises(PermissionError):
            restore_vm_lab_offline(
                self.config, backup_path=self.backup,
                preserved_current_path=self.undo, offline_gate=lambda: False
            )
        self.assertFalse(self.undo.exists())

    def test_invalid_backup_fails_before_replacing_service_ledger(self):
        self.promote()
        self.backup.write_bytes(b"not-sqlite")
        with self.assertRaises(sqlite3.Error):
            restore_vm_lab_offline(
                self.config, backup_path=self.backup,
                preserved_current_path=self.undo, offline_gate=lambda: True
            )
        with closing(Storage(self.db)) as service:
            self.assertEqual(service.get_setting(OWNER_KEY), SERVICE_ONLY)

    def test_production_path_and_unknown_owner_fail_closed(self):
        wrong = dict(self.config, Database=str(self.db.with_name("family.sqlite3")))
        with self.assertRaises((FileNotFoundError, ValueError)):
            promote_vm_lab_writer(
                wrong, backup_path=self.backup, offline_gate=lambda: True
            )
        with closing(Storage(self.db)) as writer:
            writer.set_setting(OWNER_KEY, "corrupt")
            with self.assertRaises(PermissionError):
                writer.charge(self.people[0], 1, self.day)
            with self.assertRaises(PermissionError):
                writer.charge_capped_once(
                    "a" * 32, self.people[0], 1, self.day
                )

    def test_service_restart_does_not_recreate_deleted_lease(self):
        self.promote()
        with closing(Storage(self.db)) as first:
            first.charge_capped_once("c" * 32, self.people[0], 9, self.day)
        with closing(Storage(self.db)) as restarted:
            self.assertEqual(restarted.get_setting(OWNER_KEY), SERVICE_ONLY)
            self.assertEqual(restarted.charge_capped_once(
                "c" * 32, self.people[0], 9, self.day
            ), 0)
            with self.assertRaises(PermissionError):
                restarted.charge(self.people[0], 5, self.day)
            self.assertEqual(restarted.used(self.people[0], self.day), 12)

    def test_equal_count_balance_mutation_between_snapshot_and_cutover_fails(self):
        """A concurrent UPDATE must not make rollback silently lose charges."""
        def race(source, target, *, lab_root):
            snapshot = create_vm_snapshot(source, target, lab_root=lab_root)
            with closing(sqlite3.connect(self.db)) as writer:
                writer.execute(
                    "UPDATE daily_usage SET seconds=seconds+2 WHERE person_id=?",
                    (self.people[0],)
                )
                writer.commit()  # closing() alone rolls back uncommitted writes
            return snapshot

        with patch("facekids.quota_vm_cutover.create_vm_snapshot", side_effect=race):
            with self.assertRaisesRegex(RuntimeError, "content changed"):
                self.promote()
        self.assertTrue(self.backup.exists())
        with closing(Storage(self.db)) as active:
            self.assertIsNone(active.get_setting(OWNER_KEY))
            self.assertEqual(active.used(self.people[0], self.day), 5)

    def test_rollback_requires_service_owned_database(self):
        """Never roll back a different ledger just because backup is valid."""
        create_vm_snapshot(self.db, self.backup, lab_root=self.root)
        with self.assertRaisesRegex(PermissionError, "not exclusively service-owned"):
            restore_vm_lab_offline(
                self.config, backup_path=self.backup,
                preserved_current_path=self.undo, offline_gate=lambda: True,
            )
        self.assertFalse(self.undo.exists())

    def test_stale_restore_staging_does_not_create_new_undo_image(self):
        self.promote()
        stale = self.root / "writer-restore-prepared.sqlite3"
        stale.write_bytes(b"incomplete prior attempt")
        with self.assertRaises(FileExistsError):
            restore_vm_lab_offline(
                self.config, backup_path=self.backup,
                preserved_current_path=self.undo, offline_gate=lambda: True,
            )
        self.assertFalse(self.undo.exists())
        self.assertEqual(stale.read_bytes(), b"incomplete prior attempt")

    def test_concurrent_service_receipt_replay_is_exactly_once(self):
        """Four independent SQLite connections contend for the same receipt."""
        self.promote()
        gate = Barrier(4)
        def submit_receipt(_):
            with closing(Storage(self.db)) as writer:
                gate.wait(timeout=6)
                return writer.charge_capped_once(
                    "d" * 32, self.people[1], 11, self.day
                )
        with ThreadPoolExecutor(max_workers=4) as pool:
            charged = list(pool.map(submit_receipt, range(4)))
        self.assertEqual(sorted(charged), [0, 0, 0, 11])
        with closing(Storage(self.db)) as after_restart:
            self.assertEqual(after_restart.used(self.people[1], self.day), 11)
            self.assertEqual(
                after_restart.charge_capped_once(
                    "d" * 32, self.people[1], 11, self.day
                ), 0
            )
            with self.assertRaises(PermissionError):
                after_restart.charge(self.people[1], 1, self.day)


if __name__ == "__main__":
    unittest.main()
