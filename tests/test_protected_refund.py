"""P3: synthetic idempotent refunds, no Filhos IPC write capability."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from facekids.storage import Storage


class ProtectedRefundTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "fixture.sqlite3"
        self.store = Storage(self.path)
        self.person = self.store.add_person("Synthetic", 120)
        self.date = "2026-10-27"
        self.store.set_setting("quota_writer_owner", "vm-service-only")
        self.ids = ("a" * 32, "b" * 32)
        for event in self.ids:
            self.assertEqual(self.store.charge_capped_once(
                event, self.person, 30, self.date), 30)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def refund(self, event, epoch, seconds, receipts=None):
        return self.store.refund_capped_once(
            event, epoch, self.person, seconds,
            self.ids if receipts is None else receipts, self.date)

    def test_exact_replay_new_uuid_and_same_tick_cannot_over_refund(self):
        self.assertEqual(self.refund("1"*32, "e"*32, 60), 60)
        self.assertEqual(self.refund("1"*32, "e"*32, 60), 0)
        self.assertEqual(self.refund("2"*32, "e"*32, 60), 0)
        with self.assertRaises(ValueError):
            self.refund("3"*32, "f"*32, 60)
        self.assertEqual(self.store.used(self.person, self.date), 0)
        with self.assertRaises(ValueError):
            self.refund("1"*32, "e"*32, 59)

    def test_refund_cannot_exceed_charged_amount_or_limit(self):
        self.assertEqual(self.refund("4"*32, "f"*32, 120), 60)
        with self.assertRaises(ValueError):
            self.refund("5"*32, "g"*32, 120.001)
        with self.assertRaises(ValueError):
            self.refund("5"*32, "g"*32, float("nan"))
        with self.assertRaises(ValueError):
            self.refund("5"*32, "g"*32, 1, ("x"*32,))
        with self.assertRaises(PermissionError):
            self.store.refund(self.person, 10, self.date)

    def test_concurrent_refund_same_epoch_commits_only_once(self):
        self.store.close()
        # Each contender owns an independent SQLite connection.
        def worker(event):
            other = Storage(self.path)
            try:
                return other.refund_capped_once(
                    event, "d"*32, self.person, 60, self.ids, self.date)
            finally:
                other.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(worker, ("6"*32, "7"*32)))
        self.assertEqual(sorted(result), [0, 60])
        verify = Storage(self.path)
        try:
            self.assertEqual(verify.used(self.person, self.date), 0)
        finally:
            verify.close()


if __name__ == "__main__":
    unittest.main()
