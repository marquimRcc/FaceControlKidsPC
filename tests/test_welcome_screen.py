import json
import os
from pathlib import Path
import tempfile
import unittest

from facekids.welcome_screen import format_remaining_time, load_programs_config


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


if __name__ == "__main__":
    unittest.main()
