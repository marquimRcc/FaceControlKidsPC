import json
from pathlib import Path
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
            self.assertEqual(data["password"], "1")
            self.assertEqual(data["child_id"], pid)
            self.assertEqual(data["child_name"], "Filho Smoke")
            self.assertGreater(data["remaining"], 0)


if __name__ == "__main__":
    unittest.main()
