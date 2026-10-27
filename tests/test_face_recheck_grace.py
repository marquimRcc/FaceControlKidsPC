"""P4: non-charging transient grace while honoring WTS lock/reconnect."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from facekids.quota_broker_face_binding import PrivilegedLocalFaceBinder
from facekids.quota_broker_policy import ServiceOwnedQuotaBroker
from facekids.quota_broker_wts import VerifiedWtsQuotaWorker, WtsLockTracker, WtsSnapshot
from facekids.storage import Storage


class FaceRecheckGraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.store = Storage(Path(self.temp.name) / "fixture.sqlite3")
        self.person = self.store.add_person("Demo", 120)
        self.now = 100.0
        self.sid = "S-1-5-21-10-20-30-1001"
        self.snapshot = WtsSnapshot(42, self.sid, True)
        self.locks = WtsLockTracker()
        self.locks.record_scm_event(event="unlock", session_id=42)
        self.broker = ServiceOwnedQuotaBroker(
            self.store, monotonic=lambda: self.now, today=lambda: date(2026, 10, 27))
        self.worker = VerifiedWtsQuotaWorker(
            self.broker, expected_sid=self.sid, snapshot=lambda: self.snapshot,
            locks=self.locks)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def bind(self, callback):
        return PrivilegedLocalFaceBinder(
            worker=self.worker, locks=self.locks,
            recognize_locally=callback).recognize_and_bind()

    def allow(self):
        return ("ALLOW", {"user": "Filhos", "child_id": self.person})

    def test_camera_failure_preserves_identity_but_never_charges_grace(self):
        self.assertTrue(self.bind(self.allow).accepted)
        self.now += 2
        self.assertEqual(self.worker.observe_service_tick().charged_seconds, 2)
        self.assertEqual(self.bind(lambda: ("DENY_NO_FACE", {})).reason, "face-grace")
        self.assertEqual(self.worker.verified_child_for_current_console(), self.person)
        self.now += 10
        self.assertEqual(self.worker.observe_service_tick().charged_seconds, 0)
        self.now += 21
        tick = self.worker.observe_service_tick()
        self.assertEqual(tick.reason, "face-grace-expired")
        self.assertIsNone(self.worker.verified_child_for_current_console())

    def test_race_with_lock_never_preserves_grace(self):
        self.assertTrue(self.bind(self.allow).accepted)
        def capture():
            self.locks.record_scm_event(event="lock", session_id=42)
            return ("DENY_UNKNOWN", {})
        self.assertEqual(self.bind(capture).reason, "session-changed-during-capture")
        self.assertIsNone(self.worker.verified_child_for_current_console())
        self.assertEqual(self.worker.observe_service_tick().charged_seconds, 0)

    def test_recapture_success_discards_paused_window(self):
        self.assertTrue(self.bind(self.allow).accepted)
        self.now += 7
        self.assertTrue(self.bind(self.allow).accepted)
        self.now += 1
        self.assertEqual(self.worker.observe_service_tick().charged_seconds, 1)
        self.assertEqual(self.store.used(self.person, "2026-10-27"), 1)


if __name__ == "__main__":
    unittest.main()
