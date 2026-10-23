import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from facekids.child_quota_pilot import PilotEvent
from facekids.linux_auth import FaceApproval
from facekids.linux_runtime import (
    LinuxFaceQuotaRuntime,
    LinuxRuntimeConfig,
    determine_lock_state,
    enrollments_complete,
    frame_is_usable,
    protected_data_path,
    uid_is_admin,
    uid_is_monitored_user,
    warm_up_camera,
)
from facekids.locker import unlock_linux_session
from facekids.session import (
    SessionState,
    current_linux_session_state,
    parse_loginctl_properties,
)
from facekids.storage import Storage


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

    @patch("facekids.linux_runtime.grp", None)
    @patch("facekids.linux_runtime.pwd", None)
    def test_admin_check_fails_closed_without_posix_modules(self):
        self.assertTrue(uid_is_admin(0, "wheel"))
        self.assertFalse(uid_is_admin(1000, "wheel"))
        self.assertTrue(uid_is_monitored_user(0, "filhos"))
        self.assertFalse(uid_is_monitored_user(1000, "filhos"))

    def test_black_and_uniform_frames_are_rejected(self):
        self.assertFalse(frame_is_usable(None))
        self.assertFalse(frame_is_usable(np.zeros((20, 20, 3), dtype=np.uint8)))
        self.assertFalse(frame_is_usable(np.full((20, 20, 3), 100, dtype=np.uint8)))
        varied = np.zeros((20, 20, 3), dtype=np.uint8)
        varied[::2] = 100
        self.assertTrue(frame_is_usable(varied))

    def test_candidate_reports_camera_read_failure(self):
        runtime = object.__new__(LinuxFaceQuotaRuntime)
        capture = unittest.mock.Mock()
        capture.read.return_value = (False, None)
        with self.assertRaisesRegex(RuntimeError, "parou de fornecer"):
            runtime._candidate(capture)

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

    @patch("facekids.linux_runtime.approval_still_allowed", return_value=True)
    @patch("facekids.linux_runtime.unlock_linux_session")
    def test_unlock_failure_is_rate_limited(self, unlock, _allowed):
        runtime = object.__new__(LinuxFaceQuotaRuntime)
        runtime.config = LinuxRuntimeConfig(Path("db"), Path("models"))
        runtime.store = object()
        runtime._last_unlock_request = float("-inf")
        approval = FaceApproval("4", 2, 1.0)
        unlock.side_effect = RuntimeError("logind indisponível")

        self.assertFalse(runtime._maybe_unlock(approval, 10.0, "2026-10-22"))
        self.assertFalse(runtime._maybe_unlock(approval, 11.0, "2026-10-22"))
        self.assertEqual(unlock.call_count, 1)

        unlock.side_effect = None
        self.assertTrue(runtime._maybe_unlock(approval, 21.0, "2026-10-22"))
        self.assertEqual(unlock.call_count, 2)

    def test_determine_lock_state_reasons(self):
        self.assertEqual(
            determine_lock_state(
                PilotEvent.COUNTING, curfew_active=False,
                curfew_reason="ok", enrollments_ready=False,
            ),
            (True, "cadastro facial incompleto ou revogado"),
        )
        self.assertEqual(
            determine_lock_state(
                PilotEvent.COUNTING, curfew_active=True,
                curfew_reason="Fora do horário", enrollments_ready=True,
            ),
            (True, "Fora do horário"),
        )
        self.assertEqual(
            determine_lock_state(
                PilotEvent.QUOTA_EXHAUSTED, curfew_active=False,
                curfew_reason="Dentro do horário permitido", enrollments_ready=True,
            ),
            (True, "quota esgotada"),
        )
        self.assertEqual(
            determine_lock_state(
                PilotEvent.UNCERTAIN, curfew_active=False,
                curfew_reason="Dentro do horário permitido", enrollments_ready=True,
                lock_on_uncertain=True,
            ),
            (True, "identidade não confirmada"),
        )
        self.assertEqual(
            determine_lock_state(
                PilotEvent.UNCERTAIN, curfew_active=False,
                curfew_reason="Dentro do horário permitido", enrollments_ready=True,
                lock_on_uncertain=False,
            ),
            (False, ""),
        )
        self.assertEqual(
            determine_lock_state(
                PilotEvent.COUNTING, curfew_active=False,
                curfew_reason="Dentro do horário", enrollments_ready=True,
            ),
            (False, ""),
        )

    def test_runtime_close_shuts_down_cleanly(self):
        runtime = object.__new__(LinuxFaceQuotaRuntime)
        runtime._stopping = False
        runtime.store = unittest.mock.Mock()
        mock_thread = unittest.mock.Mock()
        mock_thread.is_alive.return_value = True
        runtime._server_thread = mock_thread
        mock_socket_path = unittest.mock.Mock()
        runtime.socket_path = mock_socket_path

        runtime.close()
        self.assertTrue(runtime._stopping)
        mock_thread.join.assert_called_once_with(timeout=1.0)
        mock_socket_path.unlink.assert_called_once_with(missing_ok=True)
        runtime.store.close.assert_called_once_with()

    def test_admin_protocol_adds_child_and_reports_real_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Storage(Path(directory) / "children.sqlite3")
            runtime = object.__new__(LinuxFaceQuotaRuntime)
            runtime._admin_lock = __import__("threading").Lock()
            runtime._enrollment = None
            runtime._current_child_id = None
            runtime._session_state = SessionState.ACTIVE
            added = runtime._dispatch_admin(
                store, {"op": "add_child_and_start_enrollment", "name": "Ana", "minutes": 90}
            )
            self.assertTrue(added["ok"])
            status = runtime._dispatch_admin(store, {"op": "status"})
            self.assertEqual(status["snapshot"]["children"][0]["name"], "Ana")
            self.assertEqual(status["snapshot"]["children"][0]["dailyLimitSeconds"], 5400)
            self.assertEqual(status["snapshot"]["camera"], "ready")
            self.assertEqual(status["enrollment"]["state"], "capturing")
            runtime._dispatch_admin(store, {"op": "cancel_enrollment"})
            self.assertEqual(store.people(), [])
            store.close()

    def test_child_status_exposes_only_current_identity_without_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Storage(Path(directory) / "children.sqlite3")
            ana = store.add_person("Ana", 90)
            store.add_person("Bia", 120)
            runtime = object.__new__(LinuxFaceQuotaRuntime)
            runtime._admin_lock = __import__("threading").Lock()
            runtime._enrollment = {
                "child_id": ana, "vectors": [], "state": "capturing", "error": None,
            }
            runtime._current_child_id = ana
            runtime._session_state = SessionState.ACTIVE

            status = runtime._child_status(store)
            self.assertEqual([child["name"] for child in status["snapshot"]["children"]], ["Ana"])
            self.assertIsNone(status["enrollment"])
            runtime._current_child_id = None
            self.assertEqual(runtime._child_status(store)["snapshot"]["children"], [])
            store.close()

    def test_admin_protocol_rejects_unknown_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Storage(Path(directory) / "children.sqlite3")
            runtime = object.__new__(LinuxFaceQuotaRuntime)
            runtime._admin_lock = __import__("threading").Lock()
            runtime._enrollment = None
            for request in (
                {"op": "unknown"},
                {"op": "add_child", "name": "", "minutes": 90},
                {"op": "start_enrollment", "childId": 999},
            ):
                with self.subTest(request=request), self.assertRaises(
                    (ValueError, KeyError)
                ):
                    runtime._dispatch_admin(store, request)
            store.close()

    def test_admin_protocol_lists_and_selects_profile_photos(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Storage(Path(directory) / "children.sqlite3")
            child_id = store.add_person("Ana", 90)
            vectors = [np.full(128, index, dtype=np.float32) for index in range(12)]
            photos = [b"\xff\xd8" + bytes([index]) * 200 + b"\xff\xd9"
                      for index in range(2)]
            store.replace_embeddings_and_add_photos(child_id, vectors, photos)
            runtime = object.__new__(LinuxFaceQuotaRuntime)

            listed = runtime._dispatch_admin(
                store, {"op": "list_photos", "childId": child_id}
            )["photos"]
            self.assertEqual(len(listed), 2)
            self.assertTrue(listed[0]["dataUrl"].startswith("data:image/jpeg;base64,"))
            runtime._dispatch_admin(store, {
                "op": "select_photo", "childId": child_id, "photoId": listed[1]["id"],
            })
            selected = runtime._dispatch_admin(
                store, {"op": "list_photos", "childId": child_id}
            )["photos"]
            chosen = next(photo for photo in selected if photo["id"] == listed[1]["id"])
            self.assertTrue(chosen["selected"])
            store.close()

    def test_admin_protocol_updates_time_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Storage(Path(directory) / "children.sqlite3")
            child_id = store.add_person("Ana", 90)
            runtime = object.__new__(LinuxFaceQuotaRuntime)

            runtime._dispatch_admin(store, {
                "op": "set_daily_limit", "childId": child_id, "minutes": 120,
            })
            runtime._dispatch_admin(store, {
                "op": "add_bonus", "childId": child_id, "minutes": 30,
            })
            runtime._dispatch_admin(store, {
                "op": "set_curfew", "enabled": True, "start": "08:30", "end": "20:15",
            })

            self.assertEqual(store.people()[0][2], 7200)
            self.assertEqual(store.bonus(child_id), 1800)
            self.assertEqual(store.get_curfew_config(), (True, "08:30", "20:15"))
            for request in (
                {"op": "set_daily_limit", "childId": child_id, "minutes": True},
                {"op": "add_bonus", "childId": child_id, "minutes": 0},
                {"op": "set_curfew", "enabled": "yes", "start": "08:00", "end": "20:00"},
                {"op": "set_curfew", "enabled": True, "start": "25:00", "end": "20:00"},
            ):
                with self.subTest(request=request), self.assertRaises(ValueError):
                    runtime._dispatch_admin(store, request)
            store.close()

    def test_profile_photo_encoder_crops_a_bounded_jpeg(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[40:200, 80:240] = (40, 120, 220)
        payload = LinuxFaceQuotaRuntime._encode_profile_photo(
            frame, (100, 60, 100, 120)
        )
        self.assertIsNotNone(payload)
        self.assertTrue(payload.startswith(b"\xff\xd8"))
        self.assertLessEqual(len(payload), 100000)


if __name__ == "__main__":
    unittest.main()
