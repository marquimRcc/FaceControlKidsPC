"""Complete synthetic service-owned recognition -> WTS -> SQLite flow."""
from datetime import date
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from facekids.quota_broker_protocol import VerifiedClient, handle_broker_read
from facekids.quota_broker_runtime import ServiceOwnedQuotaRuntime
from facekids.quota_broker_wts import WtsSnapshot
from facekids.storage import Storage


class RuntimeIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="synthetic-facekids-runtime-")
        self.store = Storage(Path(self.tmp.name) / "ledger.sqlite3")
        self.people = [self.store.add_person("Synthetic " + str(i), 2)
                       for i in range(1, 4)]
        self.sid = "S-1-5-21-10-20-30-1001"
        self.snapshot = WtsSnapshot(42, self.sid, True)
        self.now = 100.0
        self.selected = self.people[0]
        self.runtime = ServiceOwnedQuotaRuntime(
            self.store, expected_windows_sid=self.sid,
            observe_wts=lambda: self.snapshot,
            capture_face_locally=lambda: ("ALLOW", {
                "child_id": self.selected, "user": "Filhos"
            }),
            monotonic=lambda: self.now,
            today=lambda: date(2026, 10, 24),
        )

    def tearDown(self):
        self.runtime.stop()
        self.store.close()
        self.tmp.cleanup()

    def test_three_profile_quota_and_lock_reidentification(self):
        self.assertFalse(self.runtime.bind_from_service_camera().accepted)
        self.runtime.on_service_session_change(8, (42,))
        self.assertTrue(self.runtime.bind_from_service_camera().accepted)
        self.now = 104
        self.assertEqual(self.runtime.service_tick().charged_seconds, 4)

        self.runtime.on_service_session_change(7, (42,))  # Win+L
        self.selected = self.people[1]  # A different child may approach
        self.now = 106
        self.assertEqual(self.runtime.service_tick().charged_seconds, 0)
        self.runtime.on_service_session_change(8, (42,))
        self.now = 109
        self.assertEqual(self.runtime.service_tick().charged_seconds, 0)
        self.assertTrue(self.runtime.bind_from_service_camera().accepted)
        self.now = 112
        self.assertEqual(self.runtime.service_tick().charged_seconds, 3)

        self.runtime.on_service_session_change(7, (42,))
        self.runtime.on_service_session_change(8, (42,))
        self.selected = self.people[2]
        self.assertTrue(self.runtime.bind_from_service_camera().accepted)
        self.now = 114
        self.assertEqual(self.runtime.service_tick().charged_seconds, 2)
        self.assertEqual(
            [self.store.used(pid, "2026-10-24") for pid in self.people],
            [4, 3, 2],
        )
        n = self.store.db.execute("SELECT COUNT(*) FROM quota_tick_receipts").fetchone()[0]
        self.assertEqual(n, 3)

    def test_lock_event_processes_during_blocked_camera_and_revokes_result(self):
        """SCM LOCK must not wait for a slow camera in another thread."""
        camera_entered = threading.Event()
        release_camera = threading.Event()
        errors = []
        outcomes = []
        runtime = ServiceOwnedQuotaRuntime(
            self.store, expected_windows_sid=self.sid,
            observe_wts=lambda: self.snapshot,
            capture_face_locally=lambda: self._wait_for_camera(
                camera_entered, release_camera),
            monotonic=lambda: self.now,
            today=lambda: date(2026, 10, 24),
        )
        worker = threading.Thread(
            target=lambda: outcomes.append(runtime.bind_from_service_camera()),
            daemon=True,
        )
        locker = threading.Thread(
            target=lambda: (
                runtime.on_service_session_change(7, (42,)),
                errors.append("delivered"),
            ),
            daemon=True,
        )
        try:
            runtime.on_service_session_change(8, (42,))
            worker.start()
            self.assertTrue(camera_entered.wait(2), "Camera did not start")
            locker.start()
            self.assertTrue(self._await_delivered(errors),
                            "SCM callback was blocked waiting for the camera")
        finally:
            release_camera.set()
            worker.join(timeout=3)
            locker.join(timeout=3)
            runtime.stop()
        self.assertFalse(worker.is_alive())
        self.assertFalse(locker.is_alive())
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].reason, "session-changed-during-capture")
        self.now += 7
        self.assertEqual(runtime.service_tick().charged_seconds, 0)
        self.assertEqual(self.store.used(self.people[0], "2026-10-24"), 0)

    def _wait_for_camera(self, entered, release):
        entered.set()
        if not release.wait(3):
            raise TimeoutError("Synthetic camera held too long")
        return "ALLOW", {"child_id": self.people[0], "user": "Filhos"}

    @staticmethod
    def _await_delivered(values):
        # Event.wait is simpler for signaling, but this also checks the
        # state update without requiring the camera thread to complete.
        import time
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            if values:
                return True
            time.sleep(0.005)
        return False

    def test_duplicate_unlock_event_requires_fresh_face(self):
        self.runtime.on_service_session_change(8, (42,))
        self.assertTrue(self.runtime.bind_from_service_camera().accepted)
        self.now += 3
        self.assertEqual(self.runtime.service_tick().charged_seconds, 3)
        self.runtime.on_service_session_change(8, (42,))
        self.now += 3
        self.assertEqual(self.runtime.service_tick().charged_seconds, 0)
        self.assertTrue(self.runtime.bind_from_service_camera().accepted)

    def test_actual_face_authenticator_is_called_only_locally_without_metadata(self):
        from unittest.mock import patch
        from facekids.auth_service import FaceAuthenticator

        auth = FaceAuthenticator(Path(self.tmp.name), Path(self.tmp.name) / "ledger.sqlite3")
        fake_reply = (
            "ALLOW", {"child_id": self.people[0], "user": "Filhos"}
        )
        with patch.object(auth, "evaluate", return_value=fake_reply) as evaluate:
            runtime = ServiceOwnedQuotaRuntime.from_service_authenticator(
                self.store, expected_windows_sid=self.sid,
                authenticator=auth, observe_wts=lambda: self.snapshot,
                monotonic=lambda: self.now, today=lambda: date(2026, 10, 24),
            )
            try:
                runtime.on_service_session_change(8, (42,))
                self.assertTrue(runtime.bind_from_service_camera().accepted)
                evaluate.assert_called_once_with(persist_unlock_metadata=False)
                self.now += 3
                self.assertEqual(runtime.service_tick().charged_seconds, 3)
            finally:
                runtime.stop()
        with self.assertRaises(ValueError):
            ServiceOwnedQuotaRuntime.from_service_authenticator(
                self.store, expected_windows_sid=self.sid,
                authenticator=lambda: fake_reply,
                observe_wts=lambda: self.snapshot,
            )

    def test_child_ipc_cannot_send_debit_or_set_enrollment(self):
        self.runtime.on_service_session_change(8, (42,))
        for body in (
            b'{"version":"FACEKIDS_QUOTA_V1","action":"CHARGE"}',
            b'{"version":"FACEKIDS_QUOTA_V1","action":"SET_CHILD","child_id":2}',
        ):
            response = handle_broker_read(
                body, VerifiedClient(self.sid, self.sid, self.people[0]),
                self.store,
            )
            self.assertEqual(response["status"], "DENY")
        self.assertEqual(self.runtime.service_tick().charged_seconds, 0)

    def test_invalid_scm_control_clears_lease(self):
        self.runtime.on_service_session_change(8, (42,))
        self.assertTrue(self.runtime.bind_from_service_camera().accepted)
        with self.assertRaises(ValueError):
            self.runtime.on_service_session_change(999, (42,))
        self.now += 5
        self.assertEqual(self.runtime.service_tick().charged_seconds, 0)

    def test_sid_change_cannot_continue_verified_lease(self):
        self.runtime.on_service_session_change(8, (42,))
        self.assertTrue(self.runtime.bind_from_service_camera().accepted)
        self.snapshot = WtsSnapshot(42, "S-1-5-18", True)
        self.now += 5
        self.assertEqual(self.runtime.service_tick().charged_seconds, 0)
        self.snapshot = WtsSnapshot(42, self.sid, True)
        self.assertEqual(self.runtime.service_tick().charged_seconds, 0)


if __name__ == "__main__":
    unittest.main()
