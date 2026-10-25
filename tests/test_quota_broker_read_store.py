from contextlib import closing
"""Broker's status reader cannot mutate the SQLite fixture."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from facekids.quota_broker_read_store import ReadOnlyQuotaView
from facekids.quota_broker_protocol import VerifiedClient, handle_broker_read
from facekids.storage import Storage


class BrokerReadStoreTests(unittest.TestCase):
    def test_status_query_never_writes_ledger(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "ledger.sqlite3"
            store = Storage(path)
            cid = store.add_person("Child", 1)
            store.charge(cid, 10, "2026-10-24")
            store.close()
            sid = "S-1-5-21-999-999-999-1001"
            identity = VerifiedClient(sid, sid, cid)
            req = b'{"version":"FACEKIDS_QUOTA_V1","action":"GET_BALANCE"}'
            with ReadOnlyQuotaView(path) as view:
                response = handle_broker_read(req, identity, view,
                                              observed_day=date(2026, 10, 24))
                self.assertEqual(response["remaining_seconds"], 50)
                self.assertTrue(response["allowed_now"])
                with self.assertRaises(sqlite3.OperationalError):
                    view._db.execute(
                        "UPDATE daily_usage SET seconds=0 WHERE person_id=?", (cid,)
                    )
            with closing(sqlite3.connect(path)) as check:
                self.assertEqual(
                    check.execute("SELECT seconds FROM daily_usage").fetchone()[0], 10
                )

    def test_refuse_nonexistent_and_non_sqlite_files(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "missing.sqlite3"
            with self.assertRaises(FileNotFoundError):
                ReadOnlyQuotaView(path)
            self.assertFalse(path.exists())
            path.write_bytes(b"not sqlite")
            with self.assertRaises(sqlite3.DatabaseError):
                with ReadOnlyQuotaView(path) as reader:
                    reader.remaining(1, "2026-10-24")

    def test_strict_identifiers_and_dates(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "ledger.sqlite3"
            s = Storage(path)
            cid = s.add_person("Child", 1)
            s.close()
            with ReadOnlyQuotaView(path) as reader:
                for invalid in (True, 0, -1, "1", None):
                    with self.subTest(person_id=invalid), self.assertRaises(ValueError):
                        reader.remaining(invalid, "2026-10-24")
                for invalid in ("2026-02-30", "2026-1-1", "", None if False else 42):
                    with self.subTest(day=invalid), self.assertRaises(ValueError):
                        reader.remaining(cid, invalid)
                self.assertEqual(reader.remaining(cid, "2026-10-24"), 60)


if __name__ == "__main__":
    unittest.main()
