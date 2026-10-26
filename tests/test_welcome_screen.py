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
        with patch.dict(os.environ, {"USERNAME": "Filhos", "FACEKIDS_TEST_ACTIVE_USER": "filhos"}), \
             patch.object(welcome_screen, "is_active_console_user_filhos", return_value=True), \
             patch.object(welcome_screen, "load_programs_config", return_value={
                 "enabled": True,
                 "programs": [{"executable": "C:\\Windows\\notepad.exe", "arguments": "", "enabled": True}]
             }), \
             patch("pathlib.Path.is_file", return_value=True), \
             patch.object(welcome_screen, "is_process_running_in_current_session", return_value=True), \
             patch("subprocess.Popen") as mock_popen:
            welcome_screen._programs_launched = False
            welcome_screen.launch_configured_programs()
            mock_popen.assert_not_called()

    def test_launch_configured_programs_runs_when_not_in_session(self):
        with patch.dict(os.environ, {"USERNAME": "Filhos", "FACEKIDS_TEST_ACTIVE_USER": "filhos"}), \
             patch.object(welcome_screen, "is_active_console_user_filhos", return_value=True), \
             patch.object(welcome_screen, "load_programs_config", return_value={
                 "enabled": True,
                 "programs": [{"executable": "C:\\Windows\\notepad.exe", "arguments": "", "enabled": True}]
             }), \
             patch("pathlib.Path.is_file", return_value=True), \
             patch.object(welcome_screen, "is_process_running_in_current_session", return_value=False), \
             patch("subprocess.Popen") as mock_popen:
            welcome_screen._programs_launched = False
            welcome_screen.launch_configured_programs()
            mock_popen.assert_called_once_with(["C:\\Windows\\notepad.exe"], shell=False)

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

    def test_welcome_window_topmost_drop(self):
        mock_root = Mock()
        app = welcome_screen.WelcomeWindow.__new__(welcome_screen.WelcomeWindow)
        app.root = mock_root
        app._drop_topmost()
        mock_root.attributes.assert_called_with("-topmost", False)

    def test_welcome_window_minimize(self):
        mock_root = Mock()
        app = welcome_screen.WelcomeWindow.__new__(welcome_screen.WelcomeWindow)
        app.root = mock_root
        app.minimize()
        mock_root.update_idletasks.assert_called_once()
        mock_root.overrideredirect.assert_called_with(False)
        mock_root.iconify.assert_called_once()

    def test_welcome_window_switch_child(self):
        mock_root = Mock()
        mock_root.state.return_value = "normal"
        mock_root.after.return_value = "job_123"

        app = welcome_screen.WelcomeWindow.__new__(welcome_screen.WelcomeWindow)
        app.root = mock_root
        app.child_id = 2
        app.child_name = "Crianca 2"
        app.remaining_seconds = 1000
        app.title_label = Mock()
        app.sub_label = Mock()
        app.time_icon_label = Mock()
        app.bar_canvas = Mock()
        app.avatar_frame = Mock()
        app.photo_image = None
        app.bar_fill = "#A6E3A1"
        app.bg_card = "#181825"
        app.accent_blue = "#38BDF8"
        app.accent_cyan = "#89DCEB"

        with patch.object(app, "_render_avatar") as mock_render, \
             patch.object(app, "_update_quota_bar") as mock_bar:
            app.switch_child(3, "Elena", 7200)
            self.assertEqual(app.child_id, 3)
            self.assertEqual(app.child_name, "Elena")
            self.assertEqual(app.remaining_seconds, 7200)
            app.title_label.config.assert_called_with(text="Olá, Elena! 👋")
            mock_render.assert_called_once()
            mock_bar.assert_called_once()
            mock_root.attributes.assert_called_with("-topmost", True)
            mock_root.lift.assert_called_once()
            mock_root.after.assert_called_with(30000, app._drop_topmost)

    def test_welcome_window_check_for_child_switch(self):
        with tempfile.TemporaryDirectory() as td:
            unlock_file = Path(td) / "last_unlock.json"
            now = time.time()
            unlock_file.write_text(
                json.dumps({
                    "child_id": 4,
                    "child_name": "Ana",
                    "remaining_seconds": 5400,
                    "timestamp": now + 10,
                }),
                encoding="utf-8",
            )
            app = welcome_screen.WelcomeWindow.__new__(welcome_screen.WelcomeWindow)
            app.child_id = 2
            app.child_name = "Crianca 2"
            app.remaining_seconds = 1000
            app._last_seen_ts = now
            with patch("facekids.welcome_screen.LAST_UNLOCK_FILE", unlock_file), \
                 patch.object(app, "switch_child") as mock_switch:
                app._check_for_child_switch()
                mock_switch.assert_called_once_with(4, "Ana", 5400)


if __name__ == "__main__":
    unittest.main()
