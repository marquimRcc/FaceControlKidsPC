import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from facekids.auth_service import FaceAuthenticator, create_security_attributes
from facekids.storage import Storage


class TestAuthService(unittest.TestCase):
    def test_security_attributes(self):
        sa = create_security_attributes()
        self.assertIsNotNone(sa.nLength)
        self.assertFalse(sa.bInheritHandle)
        from facekids.auth_service import SDDL_PERMISSIVE
        # Verifica que usuarios interativos possuem apenas leitura e escrita, nao controle total
        self.assertIn("(A;;GRGW;;;IU)", SDDL_PERMISSIVE)
        self.assertNotIn("(A;;GA;;;IU)", SDDL_PERMISSIVE)

    def test_named_pipe_descriptor_conversion_fails_closed(self):
        import facekids.auth_service as service

        failing_api = SimpleNamespace(
            ConvertStringSecurityDescriptorToSecurityDescriptorW=lambda *args: 0
        )
        with patch.object(service.sys, "platform", "win32"), \
             patch.object(service.ctypes, "windll", SimpleNamespace(advapi32=failing_api), create=True):
            with self.assertRaisesRegex(RuntimeError, "SDDL conversion"):
                create_security_attributes()

    def test_missing_named_pipe_security_api_fails_closed(self):
        import facekids.auth_service as service

        with patch.object(service.sys, "platform", "win32"), \
             patch.object(service.ctypes, "windll", SimpleNamespace(advapi32=None), create=True):
            with self.assertRaisesRegex(RuntimeError, "security API"):
                create_security_attributes()

    def test_command_routing_logic(self):
        # Exercise the actual command decoder, not a test-only copy.
        from facekids.pipe_protocol import decode_pipe_command

        self.assertEqual(decode_pipe_command(b"PING"), ("PING", None))
        self.assertEqual(decode_pipe_command(b"AUTH_QUERY\\n"), ("AUTH_QUERY", None))
        self.assertEqual(decode_pipe_command(b"QUERY"), ("QUERY", None))
        self.assertEqual(decode_pipe_command(b"UNKNOWN"), (None, "INVALID_COMMAND"))
        self.assertEqual(decode_pipe_command(b"X" * 600), (None, "INVALID_REQUEST"))
        self.assertEqual(decode_pipe_command(b"AUTH_QUERY\\x00"), (None, "INVALID_REQUEST"))

    def test_authenticator_nonexistent_db(self):
        auth = FaceAuthenticator(Path("models"), Path("nonexistent.sqlite3"))
        status, data = auth.evaluate(camera_index=0)
        self.assertEqual(status, "ERROR")
        self.assertIn("Banco de dados nao encontrado", data.get("message", ""))

    def test_authenticator_empty_enrollments(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test_empty.sqlite3"
            store = Storage(db_path)
            store.close()

            auth = FaceAuthenticator(Path("models"), db_path)
            status, data = auth.evaluate(camera_index=0)
            self.assertEqual(status, "DENY_NO_ENROLLMENT")
            self.assertIn("Nenhum rosto cadastrado", data.get("message", ""))

    def test_authenticator_contract_smoke_with_mock(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test_smoke.sqlite3"
            store = Storage(db_path)
            try:
                pid = store.add_person("Filho Smoke", 120)
                dummy_vec = np.ones(128, dtype=np.float32)
                store.add_embedding(pid, dummy_vec)
            finally:
                store.close()

            # Mock recognizer
            fake_rec = MagicMock()
            fake_rec.faces.return_value = [[10, 10, 120, 120]]
            fake_rec.features.return_value = dummy_vec
            fake_rec.identify.return_value = (pid, 0.92)

            auth = FaceAuthenticator(Path("models"), db_path, recognizer=fake_rec)

            dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, dummy_frame)

            with patch("cv2.VideoCapture", return_value=mock_cap), \
                 patch("facekids.auth_service.save_child_photo"):
                status, data = auth.evaluate(camera_index=0, timeout_seconds=1.0)

            self.assertEqual(status, "ALLOW")
            self.assertEqual(data["user"], "Filhos")
            self.assertNotIn("password", data)
            self.assertEqual(data["child_id"], pid)
            self.assertEqual(data["child_name"], "Filho Smoke")
            self.assertGreater(data["remaining"], 0)

    def test_session_zero_and_camera_probe(self):
        from facekids.auth_service import is_session_zero_or_system, probe_camera_access
        # Em plataformas nao-Windows, deve retornar False
        with patch("facekids.auth_service.sys.platform", "linux"):
            self.assertFalse(is_session_zero_or_system())

        # No Windows como SYSTEM, deve retornar True
        with patch("facekids.auth_service.sys.platform", "win32"), patch.dict("os.environ", {"USERNAME": "SYSTEM"}):
            self.assertTrue(is_session_zero_or_system())

        # No Windows como usuario interativo comum, deve retornar False
        with patch("facekids.auth_service.sys.platform", "win32"), patch.dict("os.environ", {"USERNAME": "MarcosMiniPC"}):
            self.assertFalse(is_session_zero_or_system())

        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = False
            mock_cap_cls.return_value = mock_cap
            self.assertFalse(probe_camera_access(0))

        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((10, 10, 3), dtype=np.uint8))
            mock_cap_cls.return_value = mock_cap
            self.assertTrue(probe_camera_access(0))


if __name__ == "__main__":
    unittest.main()
