"""WTS-dependent service-owned quota tests on a synthetic SQLite ledger."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from facekids.quota_broker_policy import ServiceOwnedQuotaBroker
from facekids.quota_broker_wts import WtsLockTracker, WtsSnapshot, VerifiedWtsQuotaWorker
from facekids.storage import Storage


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class WtsQuotaWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "synthetic.sqlite3")
        self.first = self.store.add_person("First", 2)
        self.second = self.store.add_person("Second", 2)
        self.sid = "S-1-5-21-123-456-789-1001"
        self.clock = Clock()
        self.state = WtsSnapshot(42, self.sid, True)
        self.locks = WtsLockTracker()
        self.broker = ServiceOwnedQuotaBroker(
            self.store, monotonic=self.clock, today=lambda: date(2026, 10, 24)
        )
        self.worker = VerifiedWtsQuotaWorker(
            self.broker, expected_sid=self.sid,
            snapshot=lambda: self.state, locks=self.locks,
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def start(self, child=None, session=42):
        return self.worker.start_trusted_face_binding(
            enrolled_child_id=self.first if child is None else child,
            session_id=session,
        )

    def tick(self, now):
        self.clock.now = now
        return self.worker.observe_service_tick()

    def test_no_debit_without_os_unlock_notification(self):
        self.assertEqual(self.start().reason, "wts-unverified")
        self.assertEqual(self.tick(104).charged_seconds, 0)
        self.assertEqual(self.store.used(self.first, "2026-10-24"), 0)

    def test_trusted_unlock_then_quota_debits_and_receipt_persists(self):
        self.locks.record_scm_event(event="unlock", session_id=42)
        self.assertEqual(self.start().reason, "verified")
        self.assertEqual(self.tick(103).charged_seconds, 3.0)
        self.assertEqual(self.store.used(self.first, "2026-10-24"), 3.0)
        receipts = self.store.db.execute("SELECT COUNT(*) FROM quota_tick_receipts").fetchone()[0]
        self.assertEqual(receipts, 1)
        self.assertEqual(self.store.used(self.second, "2026-10-24"), 0)

    def test_lock_pauses_time_and_disconnect_revokes_untrusted_session(self):
        self.locks.record_scm_event(event="unlock", session_id=42)
        self.start()
        self.assertEqual(self.tick(102).charged_seconds, 2)
        self.locks.record_scm_event(event="lock", session_id=42)
        self.assertEqual(self.tick(107).charged_seconds, 0)
        self.locks.record_scm_event(event="unlock", session_id=42)
        # A new unlock alone must NEVER resume the last child's quota:
        # the account Filhos may now be used by a different child.
        self.assertEqual(self.tick(109).charged_seconds, 0)
        self.assertEqual(self.start().reason, "verified")
        self.assertEqual(self.tick(111).charged_seconds, 2)
        self.state = WtsSnapshot(42, self.sid, False)
        self.assertEqual(self.tick(113).charged_seconds, 0)
        self.state = WtsSnapshot(42, self.sid, True)
        self.assertEqual(self.tick(115).charged_seconds, 0)
        self.assertEqual(self.store.used(self.first, "2026-10-24"), 4)

    def test_session_switch_or_token_sid_change_never_debits(self):
        self.locks.record_scm_event(event="unlock", session_id=42)
        self.start()
        self.state = WtsSnapshot(43, self.sid, True)
        self.locks.record_scm_event(event="unlock", session_id=43)
        self.assertEqual(self.tick(110).reason, "session-switched")
        self.state = WtsSnapshot(42, "S-1-5-18", True)
        self.assertEqual(self.start().reason, "wts-unverified")
        self.assertEqual(self.tick(120).charged_seconds, 0)
        self.assertEqual(self.store.used(self.first, "2026-10-24"), 0)

    def test_restart_requires_fresh_unlock_and_facial_binding(self):
        self.locks.record_scm_event(event="unlock", session_id=42)
        self.start()
        self.tick(103)
        self.locks.reset()
        self.assertEqual(self.tick(105).charged_seconds, 0)
        self.locks.record_scm_event(event="logon", session_id=42)
        self.assertEqual(self.tick(106).charged_seconds, 0)
        self.locks.record_scm_event(event="unlock", session_id=42)
        self.assertEqual(self.tick(107).charged_seconds, 0)
        self.assertEqual(self.start().reason, "verified")
        self.assertEqual(self.tick(108).charged_seconds, 1)
        self.assertEqual(self.store.used(self.first, "2026-10-24"), 4)

    def test_real_scm_callback_numbers_drive_lock_state_only(self):
        self.locks.record_windows_scm_notification(8, (42,))  # WTS_SESSION_UNLOCK
        self.assertTrue(self.locks.is_unlocked(42))
        self.locks.record_windows_scm_notification(7, (42,))  # WTS_SESSION_LOCK
        self.assertFalse(self.locks.is_unlocked(42))
        self.locks.record_windows_scm_notification(8, (42,))
        self.locks.record_windows_scm_notification(2, (42,))  # CONSOLE_DISCONNECT
        self.assertFalse(self.locks.is_unlocked(42))
        self.locks.record_windows_scm_notification(8, (42,))
        with self.assertRaises(ValueError):
            self.locks.record_windows_scm_notification(8, (42, "spoof"))
        with self.assertRaises(ValueError):
            self.locks.record_windows_scm_notification(8, [42])
        with self.assertRaises(ValueError):
            self.locks.record_windows_scm_notification(999, (42,))
        self.assertTrue(self.locks.is_unlocked(42))  # invalid callback ignored

    def test_unprivileged_wts_query_cannot_guess_sid_or_unlock(self):
        from facekids.quota_broker_wts_win import observe_console_from_system
        import os
        snapshot = observe_console_from_system()
        if os.name != "nt":
            self.assertIsNone(snapshot)
        elif snapshot is not None:
            self.assertIsInstance(snapshot, WtsSnapshot)
            self.assertTrue(snapshot.token_sid.startswith("S-1-"))
        # No SCM lock notification => no trusted face binding, regardless of
        # whether the current OS was able to return a console snapshot.
        self.assertEqual(self.start().reason, "wts-unverified")

    def test_invalid_wts_state_fails_closed(self):
        for invalid in (
            lambda: WtsSnapshot(0, self.sid, True),
            lambda: WtsSnapshot(42, self.sid, 1),
            lambda: WtsSnapshot(42, "", True),
            lambda: WtsSnapshot(42, self.sid, None),
        ):
            with self.assertRaises(ValueError):
                invalid()
        for event in ("spoof", "unknown", "AUTH_QUERY"):
            with self.assertRaises(ValueError):
                self.locks.record_scm_event(event=event, session_id=42)


if __name__ == "__main__":
    unittest.main()
