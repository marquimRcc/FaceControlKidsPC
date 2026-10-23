import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from facekids.linux_probe import ProbeResult, probe_via_daemon


class LinuxProbeTests(unittest.TestCase):
    def test_status_is_conservative(self):
        self.assertEqual(ProbeResult(False, 0, 0, 0, 0, None).status, "CAMERA_NAO_ABRIU")
        self.assertEqual(ProbeResult(True, 0, 0, 0, 1, None).status, "SEM_QUADROS")
        self.assertEqual(
            ProbeResult(True, 10, 0, 0, 1, 0.5).status,
            "QUADROS_PRETOS_OU_UNIFORMES",
        )
        self.assertEqual(
            ProbeResult(True, 10, 8, 0, 1, 80).status,
            "CAMERA_UTILIZAVEL",
        )

    def test_probe_via_daemon_handles_socket_communication(self):
        with tempfile.TemporaryDirectory() as td:
            sock_path = Path(td) / "admin.sock"
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(sock_path))
            server.listen(1)

            def serve():
                conn, _ = server.accept()
                _req = conn.recv(1024)
                conn.sendall(json.dumps({
                    "ok": True,
                    "probe": {
                        "opened": True,
                        "frames": 20,
                        "usable_frames": 18,
                        "faces_seen": 5,
                        "elapsed_seconds": 3.0,
                        "mean_brightness": 75.0,
                    }
                }).encode("utf-8") + b"\n")
                conn.close()

            t = threading.Thread(target=serve, daemon=True)
            t.start()
            try:
                res = probe_via_daemon(sock_path, 2.0)
                self.assertIsNotNone(res)
                self.assertEqual(res.status, "CAMERA_UTILIZAVEL")
                self.assertEqual(res.frames, 20)
                self.assertEqual(res.usable_frames, 18)
                self.assertEqual(res.faces_seen, 5)
                self.assertEqual(res.mean_brightness, 75.0)
            finally:
                server.close()


if __name__ == "__main__":
    unittest.main()
