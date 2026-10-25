"""Synthetic SCM host acceptance: three profiles, real SQLite receipts, race safety.

No Windows services, camera, family data or administrator permissions used.
"""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from facekids.quota_broker_protocol import VerifiedClient, handle_broker_read
from facekids.quota_broker_runtime import ServiceOwnedQuotaRuntime
from facekids.quota_broker_scm_host import ServiceOwnedScmHost
from facekids.quota_broker_wts import WtsSnapshot
from facekids.storage import Storage


class ScmHostIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="facekids-quota-host-")
        self.store = Storage(Path(self.temp.name) / "synthetic-ledger.sqlite3")
        self.children = [self.store.add_person("Fictional " + str(n), 2) for n in (1, 2, 3)]
        self.sid = "S-1-5-21-1-2-3-1002"
        self.wts = WtsSnapshot(23, self.sid, True)
        self.face = self.children[0]
        self.mono = 100.0
        self.status = "ALLOW"
        self.capture_calls = 0

        def capture():
            self.capture_calls += 1
            return self.status, {"user": "Filhos", "child_id": self.face}

        self.runtime = ServiceOwnedQuotaRuntime(
            self.store, expected_windows_sid=self.sid,
            observe_wts=lambda: self.wts, capture_face_locally=capture,
            monotonic=lambda: self.mono, today=lambda: date(2026, 10, 25),
        )
        self.host = ServiceOwnedScmHost(
            self.runtime, monotonic=lambda: self.mono,
            face_retry_seconds=15, tick_interval_seconds=1,
        )

    def tearDown(self):
        self.host.request_stop()
        self.store.close()
        self.temp.cleanup()

    def test_unlock_requires_fresh_face_then_charges_three_independent_quotas(self):
        self.assertEqual(self.host.step().charged_seconds, 0)
        self.assertEqual(self.capture_calls, 0)
        for profile, seconds in zip(self.children, (4, 3, 2)):
            self.face = profile
            self.host.on_scm_session_change(8, (23,))
            self.assertEqual(self.host.step().charged_seconds, 0)
            self.assertEqual(self.capture_calls, self.children.index(profile) + 1)
            self.mono += seconds
            self.assertEqual(self.host.step().charged_seconds, seconds)
            self.host.on_scm_session_change(7, (23,))
            self.mono += 10
            self.assertEqual(self.host.step().charged_seconds, 0)
        self.assertEqual([self.store.used(p, "2026-10-25") for p in self.children], [4, 3, 2])
        count = self.store.db.execute(
            "SELECT COUNT(*) FROM quota_tick_receipts").fetchone()[0]
        self.assertEqual(count, 3)
        self.assertEqual(self.host.charged_total, 9)

    def test_forged_client_requests_cannot_enable_face_or_charge(self):
        self.host.step()
        for packet in (
            b'{"version":"FACEKIDS_QUOTA_V1","action":"CHARGE","seconds":999999}',
            b'{"version":"FACEKIDS_QUOTA_V1","action":"SET_CHILD","child_id":3}',
        ):
            reply = handle_broker_read(
                packet, VerifiedClient(self.sid, self.sid, self.children[0]), self.store
            )
            self.assertEqual(reply["status"], "DENY")
        self.mono += 50
        self.assertEqual(self.host.step().charged_seconds, 0)
        self.assertEqual(self.capture_calls, 0)
        self.assertEqual(self.host.charged_total, 0)

    def test_denied_face_is_throttled_and_cannot_charge(self):
        self.status = "DENY"
        self.host.on_scm_session_change(8, (23,))
        self.host.step()
        self.assertEqual(self.capture_calls, 1)
        self.mono += 9
        self.host.step()
        self.assertEqual(self.capture_calls, 1)
        self.mono += 7
        self.host.step()
        self.assertEqual(self.capture_calls, 2)
        self.assertEqual(self.host.charged_total, 0)

    def test_wrong_windows_token_and_disconnect_revoke(self):
        self.host.on_scm_session_change(8, (23,))
        self.host.step()
        self.wts = WtsSnapshot(23, "S-1-5-18", True)
        self.mono += 12
        self.assertEqual(self.host.step().charged_seconds, 0)
        self.wts = WtsSnapshot(23, self.sid, True)
        self.assertEqual(self.host.step().charged_seconds, 0)
        self.host.on_scm_session_change(2, (23,))
        self.assertEqual(self.host.step().charged_seconds, 0)

    def test_stop_is_fail_closed(self):
        self.host.on_scm_session_change(8, (23,))
        self.host.step()
        self.host.request_stop()
        self.mono += 100
        self.assertEqual(self.host.step().reason, "service-stopped")
        self.host.on_scm_session_change(8, (23,))
        self.assertEqual(self.capture_calls, 1)
        self.assertEqual(self.store.used(self.children[0], "2026-10-25"), 0)

    def test_unsupported_scm_notification_fails_closed(self):
        self.host.on_scm_session_change(8, (23,))
        self.host.step()
        with self.assertRaises(ValueError):
            self.host.on_scm_session_change(555, (23,))
        self.mono += 6
        self.assertEqual(self.host.step().charged_seconds, 0)

    def test_service_camera_result_cannot_survive_lock_during_capture(self):
        started = threading.Event()
        complete = threading.Event()
        results = []
        def slow_capture():
            started.set()
            if not complete.wait(3):
                raise TimeoutError("synthetic-camera timeout")
            return "ALLOW", {"user": "Filhos", "child_id": self.children[0]}
        runtime = ServiceOwnedQuotaRuntime(
            self.store, expected_windows_sid=self.sid,
            observe_wts=lambda: self.wts, capture_face_locally=slow_capture,
            monotonic=lambda: self.mono, today=lambda: date(2026, 10, 25),
        )
        host = ServiceOwnedScmHost(runtime, monotonic=lambda: self.mono)
        host.on_scm_session_change(8, (23,))
        t = threading.Thread(target=lambda: results.append(host.step()), daemon=True)
        try:
            t.start()
            self.assertTrue(started.wait(2))
            # Callback must be delivered even though the camera is blocked.
            lock_notified = threading.Event()
            c = threading.Thread(
                target=lambda: (host.on_scm_session_change(7, (23,)), lock_notified.set()),
                daemon=True,
            )
            c.start()
            self.assertTrue(lock_notified.wait(1.5))
        finally:
            complete.set()
            t.join(4)
            host.request_stop()
        self.assertFalse(t.is_alive())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].charged_seconds, 0)
        self.assertEqual(self.store.used(self.children[0], "2026-10-25"), 0)


if __name__ == "__main__":
    unittest.main()
