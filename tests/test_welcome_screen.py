from datetime import date
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import facekids.welcome_screen as welcome_screen
from facekids.welcome_screen import (
    default_programs_config,
    format_remaining_time,
    get_current_child_info,
    load_programs_config,
)


class TestWelcomeScreen(unittest.TestCase):
    def test_format_remaining_time_zero(self):
        self.assertEqual(format_remaining_time(0), "Tempo esgotado para hoje")
        self.assertEqual(format_remaining_time(-10), "Tempo esgotado para hoje")

    def test_format_remaining_time_hours_and_minutes(self):
        # 7200 seconds = 2h 00min
        self.assertIn("2h", format_remaining_time(7200))

        # 5400 seconds = 1h 30min
        self.assertEqual(format_remaining_time(5400), "1h 30min restantes")

    def test_format_remaining_time_minutes_only(self):
        # 1200 seconds = 20 min
        self.assertEqual(format_remaining_time(1200), "20 minutos restantes")

    def test_load_programs_config(self):
        cfg = load_programs_config()
        self.assertIsInstance(cfg, dict)
        self.assertIn("enabled", cfg)
        self.assertIn("programs", cfg)

    def test_default_program_opens_brave_start_page(self):
        program = default_programs_config()["programs"][0]
        self.assertIn("BraveSoftware", program["executable"])
        self.assertEqual(program["arguments"], "")

    def test_launch_configured_programs_skips_running_process(self):
        with patch.object(welcome_screen, "is_active_console_user_filhos", return_value=True), \
             patch.object(welcome_screen, "load_programs_config", return_value={
                 "enabled": True,
                 "programs": [{"executable": "C:\\Windows\\notepad.exe", "arguments": "", "enabled": True}]
             }), \
             patch("pathlib.Path.is_file", return_value=True), \
             patch.object(welcome_screen, "is_process_running", return_value=True), \
             patch("subprocess.Popen") as mock_popen:
            welcome_screen._programs_launched = False
            welcome_screen.launch_configured_programs()
            mock_popen.assert_not_called()

    def test_programs_only_launch_for_identified_child(self):
        fake_root = Mock()
        with patch.object(welcome_screen, "is_active_console_user_filhos", return_value=True), \
             patch.object(welcome_screen, "get_current_child_info", return_value=(None, "Filho(a)", 0)), \
             patch.object(welcome_screen, "launch_configured_programs") as launch, \
             patch.object(welcome_screen.tk, "Tk", return_value=fake_root), \
             patch.object(welcome_screen, "WelcomeWindow"):
            welcome_screen.show_welcome()
        launch.assert_not_called()
        fake_root.mainloop.assert_called_once_with()

        fake_root.reset_mock()
        with patch.object(welcome_screen, "is_active_console_user_filhos", return_value=True), \
             patch.object(welcome_screen, "get_current_child_info", return_value=(2, "Miguel", 3600)), \
             patch.object(welcome_screen, "launch_configured_programs") as launch, \
             patch.object(welcome_screen.tk, "Tk", return_value=fake_root), \
             patch.object(welcome_screen, "WelcomeWindow"):
            welcome_screen.show_welcome()
        launch.assert_called_once_with()

    def test_welcome_screen_skips_when_not_filhos_console(self):
        fake_root = Mock()
        with patch.object(welcome_screen, "is_active_console_user_filhos", return_value=False), \
             patch.object(welcome_screen, "launch_configured_programs") as launch, \
             patch.object(welcome_screen.tk, "Tk", return_value=fake_root):
            welcome_screen.show_welcome()
        launch.assert_not_called()
        fake_root.mainloop.assert_not_called()

    def test_get_current_child_info_fresh(self):
        with tempfile.TemporaryDirectory() as td:
            unlock_file = Path(td) / "last_unlock.json"
            unlock_file.write_text(
                json.dumps({
                    "child_id": 3,
                    "child_name": "Crianca 3",
                    "remaining_seconds": 3600,
                    "timestamp": time.time(),
                }),
                encoding="utf-8",
            )
            with patch("facekids.welcome_screen.LAST_UNLOCK_FILE", unlock_file):
                cid, name, rem = get_current_child_info()
                self.assertEqual(cid, 3)
                self.assertEqual(name, "Crianca 3")
                self.assertGreater(rem, 0)

    def test_get_current_child_info_stale_returns_unidentified(self):
        with tempfile.TemporaryDirectory() as td:
            unlock_file = Path(td) / "last_unlock.json"
            # Timestamp 1 hora atras
            unlock_file.write_text(
                json.dumps({
                    "child_id": 3,
                    "child_name": "Crianca 3",
                    "remaining_seconds": 3600,
                    "timestamp": time.time() - 3600,
                }),
                encoding="utf-8",
            )
            with patch("facekids.welcome_screen.LAST_UNLOCK_FILE", unlock_file):
                cid, name, rem = get_current_child_info()
                self.assertIsNone(cid)
                self.assertEqual(name, "Filho(a)")
                self.assertEqual(rem, 0)

    def test_get_current_child_info_missing_returns_unidentified(self):
        with tempfile.TemporaryDirectory() as td:
            unlock_file = Path(td) / "nonexistent_last_unlock.json"
            with patch("facekids.welcome_screen.LAST_UNLOCK_FILE", unlock_file):
                cid, name, rem = get_current_child_info()
                self.assertIsNone(cid)
                self.assertEqual(name, "Filho(a)")
                self.assertEqual(rem, 0)


if __name__ == "__main__":
    unittest.main()
