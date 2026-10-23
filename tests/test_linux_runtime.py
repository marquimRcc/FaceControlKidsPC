import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from facekids.linux_auth import FaceApproval
from facekids.linux_runtime import (
    LinuxFaceQuotaRuntime,
    LinuxRuntimeConfig,
    enrollments_complete,
    frame_is_usable,
    protected_data_path,
    warm_up_camera,
)
from facekids.locker import unlock_linux_session
from facekids.session import (
    SessionState,
    current_linux_session_state,
    parse_loginctl_properties,
)


class LinuxSessionTests(unittest.TestCase):
    def test_parse_active_locked_and_unknown(self):
        self.assertEqual(
            parse_loginctl_properties("Active=yes\nState=active\nLockedHint=no\n"),
            SessionState.ACTIVE,
        )
        self.assertEqual(
            parse_loginctl_properties("Active=yes\nState=active\nLockedHint=yes\n"),
            SessionState.LOCKED,
        )
        for value in (
            "Active=yes\nState=closing\nLockedHint=no\n",
            "Active=yes\nState=active\n",
            "Active=maybe\nState=active\nLockedHint=no\n",
        ):
            self.assertEqual(parse_loginctl_properties(value), SessionState.UNKNOWN)

    def test_inactive_session_is_locked(self):
        self.assertEqual(
            parse_loginctl_properties("Active=no\nState=online\nLockedHint=no\n"),
            SessionState.LOCKED,
        )

    @patch("facekids.session.subprocess.run")
    def test_loginctl_failure_is_unknown(self, run):
        run.side_effect = subprocess.CalledProcessError(1, ["loginctl"])
        self.assertEqual(current_linux_session_state("4"), SessionState.UNKNOWN)

    def test_runtime_config_rejects_unsafe_values(self):
        with tempfile.TemporaryDirectory() as directory:
            base = {"database": Path(directory) / "db", "models": Path(directory)}
            LinuxRuntimeConfig(**base, camera=0, session_id="3").validate()
            for kwargs in (
                {"camera": -1}, {"camera": 33}, {"interval_seconds": 0.1},
                {"session_id": "3;reboot"}, {"monitored_user": "filhos;reboot"},
            ):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    LinuxRuntimeConfig(**base, **kwargs).validate()

    @patch.dict("os.environ", {"FACEKIDS_DATA_DIR": "/tmp/facekids-test"})
    def test_protected_path_can_be_redirected_for_tests(self):
        self.assertEqual(
            protected_data_path(), Path("/tmp/facekids-test/criancas.sqlite3")
        )

    def test_black_and_uniform_frames_are_rejected(self):
        self.assertFalse(frame_is_usable(None))
        self.assertFalse(frame_is_usable(np.zeros((20, 20, 3), dtype=np.uint8)))
        self.assertFalse(frame_is_usable(np.full((20, 20, 3), 100, dtype=np.uint8)))
        varied = np.zeros((20, 20, 3), dtype=np.uint8)
        varied[::2] = 100
        self.assertTrue(frame_is_usable(varied))

    def test_camera_warmup_discards_configured_frames(self):
        class Capture:
            def __init__(self):
                self.reads = 0

            def read(self):
                self.reads += 1
                return self.reads % 2 == 1, object()

        capture = Capture()
        self.assertEqual(warm_up_camera(capture, 5), 3)
        self.assertEqual(capture.reads, 5)
        for invalid in (-1, 121, 1.5, True):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                warm_up_camera(capture, invalid)

    def test_runtime_requires_samples_for_every_configured_child(self):
        vector = np.ones(128, dtype=np.float32)
        people = {1: "A", 2: "B", 3: "C"}
        complete = [
            (person_id, vector)
            for person_id in people
            for _ in range(3)
        ]
        self.assertTrue(enrollments_complete(complete, people))
        self.assertFalse(enrollments_complete(complete[:-1], people))
        self.assertTrue(enrollments_complete(complete[:3], {1: "A"}))
        self.assertFalse(enrollments_complete([], {}))
        with self.assertRaises(ValueError):
            enrollments_complete(complete, people, 0)

    def test_runtime_reloads_embeddings_and_revokes_old_approval(self):
        vector = np.ones(128, dtype=np.float32)
        initial = [(person_id, vector.copy()) for person_id in (1, 2, 3) for _ in range(3)]
        revoked = initial[:-3]
        runtime = object.__new__(LinuxFaceQuotaRuntime)
        runtime.references = initial
        runtime._reference_signature = runtime._references_signature(initial)
        runtime._last_reference_refresh = float("-inf")
        runtime.store = unittest.mock.Mock()
        runtime.store.people.return_value = [
            (1, "A", 7200), (2, "B", 7200), (3, "C", 7200)
        ]
        runtime.store.embeddings.side_effect = [initial, revoked]
        runtime.engine = unittest.mock.Mock()
        runtime.engine.people = {1: "A", 2: "B", 3: "C"}
        runtime.approvals = unittest.mock.Mock()

        self.assertTrue(runtime._refresh_references(1.0))
        runtime.approvals.reset.assert_not_called()
        self.assertFalse(runtime._refresh_references(4.0))
        runtime.approvals.reset.assert_called_once_with()
        runtime.engine.policy.pause.assert_called_once_with()
        self.assertEqual(runtime.references, revoked)

    @patch("facekids.locker.os.name", "posix")
    @patch("facekids.locker.subprocess.run")
    def test_linux_unlock_is_session_bound(self, run):
        unlock_linux_session("session_4")
        run.assert_called_once_with(
            ["loginctl", "unlock-session", "session_4"], check=True, timeout=8
        )
        with self.assertRaises(ValueError):
            unlock_linux_session("4;shutdown")

    @patch("facekids.linux_runtime.approval_still_allowed", return_value=True)
    @patch("facekids.linux_runtime.unlock_linux_session")
    def test_auto_unlock_rechecks_policy_and_rate_limits(self, unlock, allowed):
        runtime = object.__new__(LinuxFaceQuotaRuntime)
        runtime.config = LinuxRuntimeConfig(Path("db"), Path("models"))
        runtime.store = object()
        runtime.approvals = unittest.mock.Mock()
        runtime._last_unlock_request = float("-inf")
        approval = FaceApproval("4", 2, 1.0)

        self.assertTrue(runtime._maybe_unlock(approval, 3.0, "2026-10-22"))
        unlock.assert_called_once_with("4")
        runtime.approvals.reset.assert_not_called()
        self.assertFalse(runtime._maybe_unlock(approval, 5.0, "2026-10-22"))
        self.assertEqual(unlock.call_count, 1)

        runtime._last_unlock_request = float("-inf")
        allowed.return_value = False
        self.assertFalse(runtime._maybe_unlock(approval, 20.0, "2026-10-22"))
        self.assertEqual(unlock.call_count, 1)

    @patch("facekids.linux_runtime.lock_current_session")
    def test_lock_failure_is_rate_limited_without_stopping_runtime(self, lock):
        runtime = object.__new__(LinuxFaceQuotaRuntime)
        runtime._last_lock_request = float("-inf")
        runtime.engine = unittest.mock.Mock()
        lock.side_effect = RuntimeError("logind indisponível")

        self.assertFalse(runtime._maybe_lock("4", "quota encerrada", 10.0))
        self.assertFalse(runtime._maybe_lock("4", "quota encerrada", 11.0))
        lock.assert_called_once_with("4")
        runtime.engine.policy.pause.assert_not_called()

        lock.side_effect = None
        self.assertTrue(runtime._maybe_lock("4", "quota encerrada", 20.0))
        runtime.engine.policy.pause.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
