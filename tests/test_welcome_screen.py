from datetime import date
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from facekids.welcome_screen import format_remaining_time, load_programs_config, get_current_child_info


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
