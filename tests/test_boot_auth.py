import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, patch

from facekids import boot_auth
from facekids import auth_service
from facekids.windows_pipe_api import configure_kernel32


class BootAuthTests(unittest.TestCase):
    def test_deadline_policy_including_long_idle_and_driver_hang(self):
        self.assertTrue(boot_auth.worker_expired({}, 30, 30))
        self.assertFalse(boot_auth.worker_expired({"phase": "listening"}, 86400, 86400))
        self.assertFalse(boot_auth.worker_expired({"phase": "request"}, 86400, 1))
        self.assertTrue(boot_auth.worker_expired({"phase": "request"}, 86400, 15))
        self.assertFalse(boot_auth.worker_expired({"phase": "allow"}, 86400, 0))
        self.assertFalse(boot_auth.worker_expired({"phase": "pipe_setup"}, 86400, 0))
        self.assertTrue(boot_auth.worker_expired({"phase": "pipe_setup"}, 86400, 15))

    def test_atomic_status_and_corrupt_status(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "state.json"
            self.assertEqual(boot_auth.read_status(target), {})
            boot_auth.write_status(target, phase="listening", pid=42)
            self.assertEqual(boot_auth.read_status(target)["pid"], 42)
            self.assertFalse(target.with_suffix(".tmp").exists())
            target.write_text("{partial", encoding="utf-8")
            self.assertEqual(boot_auth.read_status(target), {})
            target.write_text("[]", encoding="utf-8")
            self.assertEqual(boot_auth.read_status(target), {})

    def test_supervisor_kills_only_its_stalled_child_and_alternates_backends(self):
        now = [0.0]
        children = []
        commands = []

        def sleep(seconds):
            now[0] += seconds

        def popen(command, **kwargs):
            child = MagicMock(pid=100 + len(children))
            child.returncode = None
            child.poll.side_effect = lambda: child.returncode
            child.terminate.side_effect = lambda: setattr(child, "returncode", -15)
            commands.append(command)
            children.append(child)
            return child

        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "state.json"
            boot_auth.supervise(state_path=target, popen=popen,
                                clock=lambda: now[0], sleep=sleep, max_attempts=2)
            self.assertTrue(boot_auth.read_status(target)["timed_out"])
        self.assertEqual([c[c.index("--camera-backend") + 1] for c in commands],
                         ["dshow", "msmf"])
        for child in children:
            child.terminate.assert_called_once()
            child.kill.assert_not_called()

    def test_supervisor_exited_child_does_not_kill_another_process(self):
        child = MagicMock(pid=7, returncode=20)
        child.poll.return_value = 20  # Existing interactive server owns mutex.
        with tempfile.TemporaryDirectory() as td:
            boot_auth.supervise(state_path=Path(td) / "state.json",
                                popen=MagicMock(return_value=child), max_attempts=1)
        child.terminate.assert_not_called()

    def test_backend_selection(self):
        with patch.object(auth_service.sys, "platform", "win32"):
            self.assertEqual(auth_service.camera_backend_id("dshow"), auth_service.cv2.CAP_DSHOW)
            self.assertEqual(auth_service.camera_backend_id("msmf"), auth_service.cv2.CAP_MSMF)

    def test_failed_camera_is_released(self):
        camera = MagicMock()
        camera.isOpened.return_value = False
        with patch.object(auth_service.cv2, "VideoCapture", return_value=camera):
            self.assertFalse(auth_service.probe_camera_access())
        camera.release.assert_called_once()

    def test_duplicate_exits_before_camera_probe_and_closes_handle(self):
        kernel = MagicMock()
        kernel.CreateMutexW.return_value = 0x100000042
        kernel.GetLastError.return_value = 183
        with patch.object(ctypes, "windll", types.SimpleNamespace(kernel32=kernel), create=True), \
             patch.object(auth_service, "probe_camera_access") as probe:
            self.assertEqual(auth_service.run_pipe_server(), 20)
        probe.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(0x100000042)

    def test_camera_failure_releases_mutex_for_interactive_fallback(self):
        kernel = MagicMock()
        kernel.CreateMutexW.return_value = 42
        kernel.GetLastError.return_value = 0
        with patch.object(ctypes, "windll", types.SimpleNamespace(kernel32=kernel), create=True), \
             patch.object(auth_service, "is_session_zero_or_system", return_value=True), \
             patch.object(auth_service, "probe_camera_access", return_value=False):
            self.assertEqual(auth_service.run_pipe_server(camera_backend="msmf"), 21)
        kernel.CreateNamedPipeW.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(42)

    def test_64bit_input_and_output_handles_have_explicit_signatures(self):
        # Real ctypes callback objects exercise signature configuration without
        # requiring kernel32.dll on Linux or touching Windows state in CI.
        create = ctypes.CFUNCTYPE(ctypes.c_void_p)(lambda: 0)
        close = ctypes.CFUNCTYPE(ctypes.c_int)(lambda: 1)
        api = types.SimpleNamespace(CreateFileW=create, CloseHandle=close)
        configure_kernel32(api)
        self.assertIs(api.CreateFileW.restype, wintypes.HANDLE)
        self.assertEqual(api.CloseHandle.argtypes, [wintypes.HANDLE])

    @unittest.skipUnless(auth_service.sys.platform == "win32", "Requires real Win32 named pipe")
    def test_real_pipe_once_without_webcam_or_login_changes(self):
        from facekids.filhos_agent import query_auth_service
        failures = []

        def serve():
            try:
                auth_service.run_pipe_server(once=True)
            except Exception as exc:
                failures.append(exc)

        with patch.object(auth_service, "is_session_zero_or_system", return_value=False), \
             patch.object(auth_service.FaceAuthenticator, "evaluate",
                          return_value=("DENY_UNKNOWN", {"message": "isolated CI test"})):
            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            deadline = time.monotonic() + 5
            response = None
            while response is None and time.monotonic() < deadline and not failures:
                response = query_auth_service(timeout_seconds=1)
                time.sleep(0.02)
            worker.join(timeout=5)
        self.assertFalse(worker.is_alive(), "One-shot pipe server did not exit")
        self.assertEqual(failures, [])
        self.assertIsNotNone(response)
        self.assertEqual(response["status"], "DENY_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
