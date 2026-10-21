import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from facekids.storage import Storage

class StorageTest(unittest.TestCase):
    def test_user_independent_usage_and_daily_reset(self):
        with TemporaryDirectory() as d:
            db=Storage(Path(d)/"test.sqlite3")
            a=db.add_person("A",120)
            b=db.add_person("B",120)
            db.charge(a,61,"2026-10-19")
            self.assertEqual(db.remaining(a,"2026-10-19"),7139)
            self.assertEqual(db.remaining(b,"2026-10-19"),7200)
            self.assertEqual(db.remaining(a,"2026-10-20"),7200)
            db.add_embedding(a,np.ones(128,dtype=np.float32))
            self.assertEqual(db.embeddings()[0][0],a)
            db.close()

    def test_bonus_total_capped_per_child_and_day(self):
        with TemporaryDirectory() as d:
            db = Storage(Path(d) / "quotas.sqlite3")
            a = db.add_person("Filho A", 120)
            b = db.add_person("Filho B", 120)
            day = "2026-10-20"
            db.add_bonus(a, 300, day)
            db.add_bonus(a, 180, day)
            self.assertEqual(db.bonus(a, day), 28800)
            with self.assertRaises(ValueError):
                db.add_bonus(a, 1, day)
            self.assertEqual(db.bonus(a, day), 28800)
            db.add_bonus(b, 60, day)
            db.add_bonus(a, 60, "2026-10-21")
            self.assertEqual(db.bonus(b, day), 3600)
            self.assertEqual(db.bonus(a, "2026-10-21"), 3600)
            db.close()

    def test_bonus_rejects_non_calendar_dates_and_boolean_minutes(self):
        with TemporaryDirectory() as d:
            db = Storage(Path(d) / "quotas.sqlite3")
            child = db.add_person("Filho", 120)
            for invalid in ("2026-02-30", "2026-13-01", "2026-2-1", ""):
                with self.subTest(day=invalid), self.assertRaises(ValueError):
                    db.add_bonus(child, 30, invalid)
            with self.assertRaises(ValueError):
                db.add_bonus(child, True, "2026-10-20")
            db.close()

    def test_face_erasure_keeps_time_ledger_intact(self):
        with TemporaryDirectory() as d:
            db = Storage(Path(d) / "family.sqlite3")
            a = db.add_person("A", 120)
            b = db.add_person("B", 120)
            sample = np.ones(128, dtype=np.float32)
            db.add_embedding(a, sample)
            db.add_embedding(b, sample)
            db.charge(a, 90, "2026-10-20")
            self.assertEqual(db.remove_embeddings(a), 1)
            self.assertEqual(db.remove_embeddings(a), 0)
            self.assertEqual(db.enrollment_count(b), 1)
            self.assertEqual(db.remaining(a, "2026-10-20"), 7110)
            with self.assertRaises(KeyError):
                db.remove_embeddings(987)
            db.close()

    def test_update_person_name(self):
        with TemporaryDirectory() as d:
            db = Storage(Path(d) / "family.sqlite3")
            cid = db.add_person("Crianca 1", 120)
            self.assertEqual(db.get_person("Crianca 1")[0], cid)
            db.update_person_name(cid, "Lucas")
            self.assertIsNone(db.get_person("Crianca 1"))
            self.assertEqual(db.get_person("Lucas")[0], cid)
            with self.assertRaises(ValueError):
                db.update_person_name(cid, "   ")
            with self.assertRaises(KeyError):
                db.update_person_name(9999, "Novo")
            db.close()
