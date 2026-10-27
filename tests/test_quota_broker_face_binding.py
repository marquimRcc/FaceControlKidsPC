"""Pure co-located face binding checks on synthetic data; no webcam/SCM."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from facekids.quota_broker_face_binding import PrivilegedLocalFaceBinder
from facekids.quota_broker_policy import ServiceOwnedQuotaBroker
from facekids.quota_broker_wts import VerifiedWtsQuotaWorker, WtsLockTracker, WtsSnapshot
from facekids.storage import Storage


class PrivilegedFaceBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.store = Storage(Path(self.temp.name) / "fake-ledger.sqlite3")
        self.child = self.store.add_person("Test Child", 2)
        self.sid = "S-1-5-21-10-20-30-1001"
        self.clock = 100.0
        self.snapshot = WtsSnapshot(42, self.sid, True)
        self.locks = WtsLockTracker()
        self.locks.record_scm_event(event="unlock", session_id=42)
        self.broker = ServiceOwnedQuotaBroker(
            self.store, monotonic=lambda: self.clock,
            today=lambda: date(2026, 10, 24),
        )
        self.worker = VerifiedWtsQuotaWorker(
            self.broker, expected_sid=self.sid,
            snapshot=lambda: self.snapshot, locks=self.locks,
        )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def bind(self, recognize=None):
        callback = recognize or (lambda: (
            "ALLOW", {"child_id": self.child, "user": "Filhos", "remaining": 120}
        ))
        return PrivilegedLocalFaceBinder(
            worker=self.worker, locks=self.locks, recognize_locally=callback,
        ).recognize_and_bind()

    def test_co_located_face_recognition_assigns_ledger_to_enrolled_child(self):
        result = self.bind()
        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "verified")
        self.clock = 103.0
        self.assertEqual(self.worker.observe_service_tick().charged_seconds, 3.0)
        self.assertEqual(self.store.used(self.child, "2026-10-24"), 3.0)

    def test_invalid_response_cannot_retain_prior_lease(self):
        self.assertTrue(self.bind().accepted)
        for reply in [
            ("ALLOW", {"child_id": True, "user": "Filhos"}),
            ("ALLOW", {"child_id": self.child, "user": "Administrator"}),
            ("DENY_UNKNOWN", {"child_id": self.child, "user": "Filhos"}),
            ("ALLOW", {"child_id": 999999, "user": "Filhos"}),
            ("ALLOW", "not a mapping"),
        ]:
            with self.subTest(reply=reply):
                self.assertFalse(self.bind(lambda response=reply: response).accepted)
                self.clock += 2
                self.assertEqual(self.worker.observe_service_tick().charged_seconds, 0)
                self.assertTrue(self.bind().accepted)

    def test_locks_during_face_capture_rejects_stale_result(self):
        def race():
            self.locks.record_scm_event(event="lock", session_id=42)
            self.locks.record_scm_event(event="unlock", session_id=42)
            return "ALLOW", {"child_id": self.child, "user": "Filhos"}
        self.assertEqual(self.bind(race).reason, "session-changed-during-capture")
        self.assertEqual(self.worker.observe_service_tick().charged_seconds, 0)

    def test_identity_switch_during_capture_rejects_response(self):
        def race():
            self.snapshot = WtsSnapshot(43, self.sid, True)
            return "ALLOW", {"child_id": self.child, "user": "Filhos"}
        self.assertFalse(self.bind(race).accepted)

    def test_camera_error_and_locked_session_never_bind(self):
        self.assertEqual(self.bind(lambda: (_ for _ in ()).throw(RuntimeError())).reason,
                         "local-recognizer-error")
        self.locks.record_scm_event(event="lock", session_id=42)
        self.assertEqual(self.bind().reason, "session-unverified")
        self.clock = 104
        self.assertEqual(self.worker.observe_service_tick().charged_seconds, 0)


if __name__ == "__main__":
    unittest.main()
