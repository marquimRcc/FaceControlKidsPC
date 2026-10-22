import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from facekids.linux_runtime import (
    LinuxRuntimeConfig,
    frame_is_usable,
    protected_data_path,
)
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


if __name__ == "__main__":
    unittest.main()
