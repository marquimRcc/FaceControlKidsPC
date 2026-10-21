import unittest
from pathlib import Path
from facekids.auth_service import FaceAuthenticator, create_security_attributes

class TestAuthService(unittest.TestCase):
    def test_security_attributes(self):
        sa = create_security_attributes()
        self.assertIsNotNone(sa.nLength)
        self.assertFalse(sa.bInheritHandle)

    def test_authenticator_nonexistent_db(self):
        auth = FaceAuthenticator(Path("models"), Path("nonexistent.sqlite3"))
        status, data = auth.evaluate(camera_index=0)
        self.assertEqual(status, "ERROR")

if __name__ == "__main__":
    unittest.main()
