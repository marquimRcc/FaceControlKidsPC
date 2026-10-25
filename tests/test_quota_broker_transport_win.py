"""Windows-only *synthetic* local named-pipe broker smoke tests."""
import csv
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import threading
import time
import unittest
import uuid

from facekids.storage import Storage
from facekids.quota_broker_client_win import query_lab_balance
from facekids.quota_broker_transport_win import LAB_PIPE_PREFIX, serve_one_lab_request


@unittest.skipUnless(os.name == "nt", "Windows local pipe API only")
class LabBrokerWindowsTests(unittest.TestCase):
    def _current_sid(self) -> str:
        line = subprocess.check_output(
            ["whoami.exe", "/user", "/fo", "csv", "/nh"], text=True,
        ).strip()
        return next(csv.reader([line]))[-1].strip()

    def _exercise_pipe(self, sid_to_child, *, via_client=False):
        with TemporaryDirectory() as td:
            root = Path(td) / "facekids-quota-lab"
            root.mkdir()
            db = root / "ledger.sqlite3"
            storage = Storage(db)
            storage.add_person("Child", 1)
            storage.close()
            pipe = LAB_PIPE_PREFIX + uuid.uuid4().hex
            errors = []

            def server():
                try:
                    serve_one_lab_request(
                        pipe_name=pipe, data_path=db,
                        enrolled_child_by_sid=sid_to_child
                    )
                except Exception as exc:
                    errors.append(exc)

            worker = threading.Thread(target=server, daemon=True)
            worker.start()
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
            k.WaitNamedPipeW.restype = wintypes.BOOL
            k.CreateFileW.argtypes = [
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
            ]
            k.CreateFileW.restype = wintypes.HANDLE
            k.WriteFile.argtypes = [
                wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
            ]
            k.WriteFile.restype = wintypes.BOOL
            k.ReadFile.argtypes = [
                wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
            ]
            k.ReadFile.restype = wintypes.BOOL
            k.CloseHandle.argtypes = [wintypes.HANDLE]
            k.CloseHandle.restype = wintypes.BOOL

            ready = False
            for _ in range(100):
                if k.WaitNamedPipeW(pipe, 50):
                    ready = True
                    break
                time.sleep(0.02)
            self.assertTrue(ready, f"pipe not ready: {errors}")
            if via_client:
                reply = query_lab_balance(pipe)
            else:
                handle = k.CreateFileW(pipe, 0xC0000000, 0, None, 3, 0, None)
                self.assertNotIn(handle, (None, 0, ctypes.c_void_p(-1).value))
                try:
                    request = b'{"version":"FACEKIDS_QUOTA_V1","action":"GET_BALANCE"}'
                    sent = wintypes.DWORD()
                    buf = ctypes.create_string_buffer(request)
                    self.assertTrue(k.WriteFile(
                        handle, buf, len(request), ctypes.byref(sent), None
                    ))
                    self.assertEqual(sent.value, len(request))
                    result = ctypes.create_string_buffer(2048)
                    read = wintypes.DWORD()
                    ok = k.ReadFile(handle, result, 2047, ctypes.byref(read), None)
                    self.assertTrue(ok, f"GetLastError={ctypes.get_last_error()}, server={errors}")
                    reply = json.loads(result.raw[:read.value].decode("ascii"))
                finally:
                    k.CloseHandle(handle)
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors, f"server errors: {errors}")
            return reply

    def test_accepted_real_token_is_limited_to_enrolled_child(self):
        self.assertEqual(
            self._exercise_pipe({self._current_sid(): 1})["remaining_seconds"],
            60,
        )

    def test_reusable_read_only_client_round_trip(self):
        self.assertEqual(
            self._exercise_pipe({self._current_sid(): 1}, via_client=True)["remaining_seconds"], 60,
        )

    def test_sid_not_in_protected_mapping_is_denied(self):
        self.assertEqual(self._exercise_pipe({"S-1-5-18": 1}), {"status": "DENY"})

    def test_no_host_on_wrong_platform_or_without_lab_path(self):
        # Pure preflight runs before any OS resource is opened.
        with self.assertRaises(ValueError):
            serve_one_lab_request(
                pipe_name=r"\\.\pipe\FaceKidsAuthPipe", data_path=Path("unknown"),
                enrolled_child_by_sid={"S-1-5-18": 1},
            )


if __name__ == "__main__":
    unittest.main()
