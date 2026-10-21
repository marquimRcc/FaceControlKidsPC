import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

from facekids.filhos_agent import QuotaTracker, read_last_unlock_child
from facekids.storage import Storage


class TestFilhosAgent(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.store = Storage(self.db_path)
        self.child_id = self.store.add_person("Lucas", 120)

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_switch_child(self):
        tracker = QuotaTracker(self.store)
        tracker.warned_10m = True
        tracker.switch_child(self.child_id, "Lucas")
        self.assertEqual(tracker.current_child_id, self.child_id)
        self.assertEqual(tracker.current_child_name, "Lucas")
        self.assertFalse(tracker.warned_10m)

    def test_update_balance_resets_warnings(self):
        tracker = QuotaTracker(self.store)
        tracker.warned_1m = True
        tracker.warned_5m = True
        tracker.warned_10m = True

        # Bonus given: remaining now > 600s
        tracker.update_balance(700)
        self.assertFalse(tracker.warned_1m)
        self.assertFalse(tracker.warned_5m)
        self.assertFalse(tracker.warned_10m)

    @patch("facekids.filhos_agent.show_toast")
    @patch("facekids.filhos_agent.lock_current_session")
    def test_notifications_and_lock_progression(self, mock_lock, mock_toast):
        tracker = QuotaTracker(self.store)
        tracker.switch_child(self.child_id, "Lucas")

        # 1. Above 10m (> 600s): No notification, no lock
        locked = tracker.check_notifications_and_lock(650)
        self.assertFalse(locked)
        mock_toast.assert_not_called()
        mock_lock.assert_not_called()

        # 2. At 10m (<= 600s): Warning 10m triggered
        locked = tracker.check_notifications_and_lock(590)
        self.assertFalse(locked)
        self.assertTrue(tracker.warned_10m)
        self.assertEqual(mock_toast.call_count, 1)

        # 3. At 5m (<= 300s): Warning 5m triggered
        locked = tracker.check_notifications_and_lock(280)
        self.assertFalse(locked)
        self.assertTrue(tracker.warned_5m)
        self.assertEqual(mock_toast.call_count, 2)

        # 4. At 1m (<= 60s): Warning 1m triggered
        locked = tracker.check_notifications_and_lock(45)
        self.assertFalse(locked)
        self.assertTrue(tracker.warned_1m)
        self.assertEqual(mock_toast.call_count, 3)

        # 5. At 0s: Lock triggered!
        locked = tracker.check_notifications_and_lock(0)
        self.assertTrue(locked)
        mock_lock.assert_called_once()
        self.assertEqual(mock_toast.call_count, 4)

    def test_read_last_unlock_child(self):
        with tempfile.TemporaryDirectory() as td:
            unlock_file = Path(td) / "last_unlock.json"
            unlock_file.write_text(
                json.dumps({"child_id": 2, "child_name": "Crianca 2"}),
                encoding="utf-8",
            )
            with patch("facekids.filhos_agent.LAST_UNLOCK_FILE", unlock_file):
                cid, cname = read_last_unlock_child()
                self.assertEqual(cid, 2)
                self.assertEqual(cname, "Crianca 2")

    def test_read_last_unlock_child_stale_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            unlock_file = Path(td) / "last_unlock.json"
            unlock_file.write_text(
                json.dumps({
                    "child_id": 2,
                    "child_name": "Crianca 2",
                    "timestamp": time.time() - 1200,
                }),
                encoding="utf-8",
            )
            with patch("facekids.filhos_agent.LAST_UNLOCK_FILE", unlock_file):
                cid, cname = read_last_unlock_child()
                self.assertIsNone(cid)
                self.assertEqual(cname, "")

    def test_unidentified_child_state_safe(self):
        tracker = QuotaTracker(self.store)
        self.assertIsNone(tracker.current_child_id)
        # Notifications should use fallback name without crashing
        with patch("facekids.filhos_agent.show_toast"):
            tracker.check_notifications_and_lock(500)
            self.assertTrue(tracker.warned_10m)


if __name__ == "__main__":
    unittest.main()
