"""Integrated disposable quota acceptance: NO family DB, Winlogon or installs.

Uses three made-up profiles, one shared synthetic Windows SID, SCM/WTS events,
durable tick receipts and a WAL-consistent SQLite backup/restore. OS token ACL
and real SCM installation are tested by separate Windows-only CI steps.
"""
from __future__ import annotations

import json
from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from facekids.quota_broker_policy import ServiceOwnedQuotaBroker
from facekids.quota_broker_protocol import VerifiedClient, handle_broker_read
from facekids.quota_broker_wts import WtsLockTracker, WtsSnapshot, VerifiedWtsQuotaWorker
from facekids.storage import Storage

DAY = "2026-10-24"
SID = "S-1-5-21-90-80-70-1001"


class DeterministicClock:
    def __init__(self) -> None:
        self.seconds = 100.0

    def __call__(self) -> float:
        return self.seconds


def run_synthetic_acceptance() -> dict[str, object]:
    # All file paths are allocated inside a disposable tempfile; never read
    # C:\ProgramData\FaceKids or any path from child-supplied IPC.
    with TemporaryDirectory(prefix="facekids-quota-accept-") as root:
        directory = Path(root)
        database = directory / "synthetic-only.sqlite3"
        backup_path = directory / "snapshot-only.sqlite3"
        store = Storage(database)
        try:
            child_ids = [
                store.add_person("Synthetic Child 1", 2),
                store.add_person("Synthetic Child 2", 2),
                store.add_person("Synthetic Child 3", 2),
            ]
            clock = DeterministicClock()
            session = [WtsSnapshot(42, SID, True)]
            locks = WtsLockTracker()
            broker = ServiceOwnedQuotaBroker(
                store, monotonic=clock, today=lambda: date(2026, 10, 24)
            )
            worker = VerifiedWtsQuotaWorker(
                broker, expected_sid=SID, snapshot=lambda: session[0],
                locks=locks,
            )

            def tick(at: int) -> float:
                clock.seconds = float(at)
                return worker.observe_service_tick().charged_seconds

            def bind(idx: int) -> None:
                result = worker.start_trusted_face_binding(
                    enrolled_child_id=child_ids[idx], session_id=session[0].session_id
                )
                assert result.reason == "verified", result.reason

            # Unknown WTS state cannot debit, even if child requests it.
            assert worker.start_trusted_face_binding(
                enrolled_child_id=child_ids[0], session_id=42
            ).reason == "wts-unverified"
            assert tick(102) == 0

            # First child after trusted face binding + real SCM-style unlock.
            locks.record_windows_scm_notification(8, (42,))
            bind(0)
            assert tick(106) == 4
            assert store.used(child_ids[0], DAY) == 4

            # A child can be replaced while locked: old face lease must die.
            locks.record_windows_scm_notification(7, (42,))
            assert tick(108) == 0
            locks.record_windows_scm_notification(8, (42,))
            assert tick(110) == 0  # unlock is NOT facial re-identification
            bind(1)
            assert tick(113) == 3
            assert store.used(child_ids[0], DAY) == 4
            assert store.used(child_ids[1], DAY) == 3

            # Switching sessions invalidates second child's lease.
            session[0] = WtsSnapshot(43, SID, True)
            locks.record_windows_scm_notification(8, (43,))
            assert tick(117) == 0
            session[0] = WtsSnapshot(42, SID, True)
            locks.record_windows_scm_notification(8, (42,))
            assert tick(119) == 0
            bind(2)
            assert tick(121) == 2

            # The client-facing protocol MUST remain read-only, irrespective of
            # what fields an untrusted child invents.
            identity = VerifiedClient(SID, SID, child_ids[2])
            forged = json.dumps({
                "version": "FACEKIDS_QUOTA_V1",
                "action": "CHARGE", "seconds": 9000,
                "child_id": child_ids[0], "session_id": 42,
            }).encode()
            assert handle_broker_read(forged, identity, store)["status"] == "DENY"
            assert [store.used(child, DAY) for child in child_ids] == [4, 3, 2]

            # Durable receipts are written in the same transaction as debits.
            receipt_count = store.db.execute(
                "SELECT COUNT(*) FROM quota_tick_receipts"
            ).fetchone()[0]
            assert receipt_count == 3, receipt_count

            # SQLite .backup is WAL-consistent; restore a disposable fixture.
            # sqlite3 Connection's context manager commits but does NOT close
            # the OS handle. Explicit closing is mandatory for Windows rollback.
            with closing(sqlite3.connect(backup_path)) as backup:
                store.db.backup(backup)
            assert tick(123) == 2
            assert store.used(child_ids[2], DAY) == 4
        finally:
            store.close()

        # No active SQLite connections at the cutover boundary.
        with closing(sqlite3.connect(backup_path)) as restored_source:
            with closing(sqlite3.connect(database)) as target:
                restored_source.backup(target)
        reopened = Storage(database)
        try:
            balances = [reopened.used(child, DAY) for child in child_ids]
            assert balances == [4, 3, 2], balances
            count_after_restore = reopened.db.execute(
                "SELECT COUNT(*) FROM quota_tick_receipts"
            ).fetchone()[0]
            assert count_after_restore == 3
        finally:
            reopened.close()

        # SQLite mode=ro is a supplemental check, not NTFS token isolation.
        ro = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
        try:
            try:
                ro.execute("UPDATE daily_usage SET seconds=0")
            except sqlite3.OperationalError as exc:
                assert "readonly" in str(exc).lower(), str(exc)
            else:
                raise AssertionError("Read-only SQLite connection permitted write")
        finally:
            ro.close()
        return {
            "mode": "disposable-synthetic",
            "profile_count": 3,
            "shared_windows_sid": True,
            "quota_seconds_after_rollback": [4, 3, 2],
            "durable_receipts": receipt_count,
            "new_face_binding_required_after_lock": True,
            "child_ipc_mutation_denied": True,
            "wal_snapshot_restored": True,
            "sqlite_read_only_write_denied": True,
            "real_windows_logon_tested": False,
            "real_family_data_accessed": False,
        }


def main() -> int:
    evidence = run_synthetic_acceptance()
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
