"""Synthetic metadata validation; no webcam, biometrics, or Windows login."""
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from facekids.unlock_event import validated_unlock_event, enrolled_display_name
from facekids.storage import Storage
from facekids.filhos_agent import read_last_unlock_child


class UnlockEventTests(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.event = {
            "child_id": 2, "child_name": "Crianca 2",
            "timestamp": self.now - 2.0,
        }

    def test_recent_valid_event_preserves_identity(self):
        self.assertEqual(
            validated_unlock_event(self.event, now=self.now),
            (2, "Crianca 2", self.event["timestamp"])
        )

    def test_reject_stale_and_future_even_if_date_matches(self):
        for timestamp in (self.now - 600, self.now - 1200, self.now + 3, 0, -1):
            with self.subTest(timestamp=timestamp):
                self.assertIsNone(validated_unlock_event(
                    {**self.event, "timestamp": timestamp}, now=self.now
                ))

    def test_reject_boolean_fractional_or_invalid_child_ids(self):
        for child_id in (True, False, 0, -1, "2", 2.0, None, [], {}):
            with self.subTest(child_id=child_id):
                self.assertIsNone(validated_unlock_event(
                    {**self.event, "child_id": child_id}, now=self.now
                ))

    def test_reject_nonfinite_time_or_missing_fields(self):
        for timestamp in (float("nan"), float("inf"), -float("inf"), True, "1000"):
            with self.subTest(timestamp=str(timestamp)):
                self.assertIsNone(validated_unlock_event(
                    {**self.event, "timestamp": timestamp}, now=self.now
                ))
        for event in (None, {}, [], "event", {"child_id": 2}):
            self.assertIsNone(validated_unlock_event(event, now=self.now))

    def test_reject_invalid_child_names(self):
        for name in ("", "   ", "x" * 81, 123, None):
            self.assertIsNone(validated_unlock_event(
                {**self.event, "child_name": name}, now=self.now
            ))

    def test_enrolled_name_not_overwritten_by_untrusted_notification(self):
        with TemporaryDirectory() as td:
            store = Storage(Path(td) / "enrollments.sqlite3")
            try:
                valid_id = store.add_person("Real profile", 120)
                fake_file = {**self.event, "child_id": valid_id, "child_name": "Forged name"}
                event = validated_unlock_event(fake_file, now=self.now)
                self.assertIsNotNone(event)
                self.assertEqual(enrolled_display_name(store, event[0]), "Real profile")
                self.assertIsNone(enrolled_display_name(store, 999999))
                for invalid_id in (0, -1, True, str(valid_id), None):
                    self.assertIsNone(enrolled_display_name(store, invalid_id))
            finally:
                store.close()

    def test_file_reader_rejects_future_and_bad_id(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "last_unlock.json"
            with patch("facekids.filhos_agent.LAST_UNLOCK_FILE", path):
                for candidate in (
                    {**self.event, "timestamp": self.now + 3600},
                    {**self.event, "child_id": True},
                    {**self.event, "timestamp": "invalid"},
                ):
                    path.write_text(json.dumps(candidate), encoding="utf-8")
                    self.assertEqual(read_last_unlock_child(), (None, "", 0.0))
                path.write_text(json.dumps(self.event), encoding="utf-8")
                self.assertEqual(read_last_unlock_child()[0], 2)


if __name__ == "__main__":
    unittest.main()
