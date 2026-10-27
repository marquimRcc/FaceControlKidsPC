"""P0/P4 in-process SCM connector must not publish unlock notifications."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from facekids.auth_service import FaceAuthenticator
from facekids.quota_broker_runtime import ServiceOwnedQuotaRuntime
from facekids.quota_broker_wts import WtsSnapshot
from facekids.storage import Storage


class ScmRecognizerContract(unittest.TestCase):
    def test_uses_side_effect_free_recognition_and_pauses_on_camera_error(self):
        with TemporaryDirectory() as root:
            store = Storage(Path(root) / "fixture.sqlite3")
            try:
                child = store.add_person("Mock Child", 120)
                authenticator = FaceAuthenticator(Path("models"), Path(root) / "fixture.sqlite3")
                now = [100.0]
                token = "S-1-5-21-10-20-30-1001"
                runtime = ServiceOwnedQuotaRuntime.from_service_authenticator(
                    store, expected_windows_sid=token,
                    authenticator=authenticator,
                    observe_wts=lambda: WtsSnapshot(42, token, True),
                    monotonic=lambda: now[0],
                    today=lambda: date(2026, 10, 27))
                runtime.on_service_session_change(8, (42,))
                with patch.object(authenticator, "evaluate", return_value=(
                    "ALLOW", {"child_id": child, "user": "Filhos"})) as recognized:
                    self.assertTrue(runtime.bind_from_service_camera().accepted)
                    recognized.assert_called_once_with(publish_unlock_event=False)
                now[0] += 2
                self.assertEqual(runtime.service_tick().charged_seconds, 2)
                with patch.object(authenticator, "evaluate",
                                  side_effect=RuntimeError("camera lost")):
                    result = runtime.bind_from_service_camera()
                    self.assertEqual(result.reason, "face-grace")
                now[0] += 3
                self.assertEqual(runtime.service_tick().charged_seconds, 0)
                runtime.on_service_session_change(7, (42,))
                self.assertIsNone(runtime.verified_child_for_client(token_sid=token))
                self.assertEqual(runtime.service_tick().charged_seconds, 0)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
