import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from facekids.storage import Storage


class StorageTest(unittest.TestCase):
    def test_profile_photos_are_local_selectable_and_separate_from_embeddings(self):
        with TemporaryDirectory() as d:
            db = Storage(Path(d) / "photos.sqlite3")
            child = db.add_person("Ana", 90)
            vectors = [np.ones(128, dtype=np.float32) * (index + 1)
                       for index in range(12)]
            photos = [b"\xff\xd8" + bytes([index]) * 200 + b"\xff\xd9"
                      for index in range(3)]
            db.replace_embeddings_and_add_photos(child, vectors, photos)
            gallery = db.profile_photos(child)
            self.assertEqual(len(gallery), 3)
            self.assertEqual(db.enrollment_count(child), 12)
            self.assertEqual(sum(selected for _id, _jpeg, selected in gallery), 1)
            chosen = gallery[1][0]
            db.select_profile_photo(child, chosen)
            self.assertEqual(db.selected_profile_photo(child), gallery[1][1])
            self.assertEqual(db.enrollment_count(child), 12)
            with self.assertRaises(KeyError):
                db.select_profile_photo(child, 9999)
            # Testa clear_profile_photos
            cleared = db.clear_profile_photos(child)
            self.assertEqual(cleared, 3)
            self.assertEqual(len(db.profile_photos(child)), 0)
            self.assertEqual(db.enrollment_count(child), 12)  # embeddings intact
            db.close()

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
            # Testa reembolso de inatividade
            db.refund(a, 39, "2026-10-19")
            self.assertEqual(db.remaining(a, "2026-10-19"), 7178)
            with self.assertRaises(ValueError):
                db.refund(a, -10, "2026-10-19")
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

    def test_delete_person_removes_profile_and_all_associated_data(self):
        with TemporaryDirectory() as d:
            db = Storage(Path(d) / "family.sqlite3")
            child = db.add_person("Lucas", 120)
            other = db.add_person("Bia", 90)
            db.add_embedding(child, np.ones(128, dtype=np.float32))
            db.charge(child, 90, "2026-10-20")
            db.add_bonus(child, 30, "2026-10-20")
            photo = b"\xff\xd8" + b"x" * 200 + b"\xff\xd9"
            db.db.execute(
                "INSERT INTO profile_photos(person_id,jpeg,selected) VALUES (?,?,1)",
                (child, photo),
            )
            db.db.commit()

            db.delete_person(child)

            self.assertEqual([row[0] for row in db.people()], [other])
            for table in ("embeddings", "daily_usage", "daily_bonus", "profile_photos"):
                count = db.db.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE person_id=?", (child,)
                ).fetchone()[0]
                self.assertEqual(count, 0, table)
            with self.assertRaises(KeyError):
                db.delete_person(child)
            with self.assertRaises(ValueError):
                db.delete_person(True)
            db.close()

    def test_get_history(self):
        with TemporaryDirectory() as d:
            db = Storage(Path(d) / "family.sqlite3")
            cid = db.add_person("Lucas", 120)
            from datetime import date, timedelta
            today = date.today().isoformat()
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            db.charge(cid, 3600, today)
            db.charge(cid, 1800, yesterday)
            history = db.get_history(cid, 7)
            self.assertEqual(len(history), 7)
            self.assertEqual(history[-1], (today, 3600.0))
            self.assertEqual(history[-2], (yesterday, 1800.0))
            db.close()

    def test_curfew_config_and_active_check(self):
        with TemporaryDirectory() as d:
            db = Storage(Path(d) / "family.sqlite3")
            # Default disabled
            enabled, start, end = db.get_curfew_config()
            self.assertFalse(enabled)
            self.assertEqual(start, "08:00")
            self.assertEqual(end, "20:00")

            is_blocked, _ = db.is_curfew_active("22:00")
            self.assertFalse(is_blocked)  # Not blocked because disabled

            # Enable curfew 08:00 to 20:00
            db.set_curfew_config(True, "08:00", "20:00")
            enabled, start, end = db.get_curfew_config()
            self.assertTrue(enabled)

            # Within hours
            is_blocked, msg = db.is_curfew_active("14:30")
            self.assertFalse(is_blocked)
            self.assertIn("Dentro", msg)

            # Outside hours (at night)
            is_blocked, msg = db.is_curfew_active("21:15")
            self.assertTrue(is_blocked)
            self.assertIn("Fora", msg)

            # Outside hours (early morning)
            is_blocked, msg = db.is_curfew_active("06:30")
            self.assertTrue(is_blocked)

            db.close()

    def test_parent_pin(self):
        with TemporaryDirectory() as d:
            db = Storage(Path(d) / "family.sqlite3")
            self.assertIsNone(db.get_parent_pin())
            self.assertTrue(db.verify_parent_pin("1234"))  # Sem PIN aceita qualquer um

            db.set_parent_pin("9876")
            self.assertIsNotNone(db.get_parent_pin())
            self.assertTrue(db.verify_parent_pin("9876"))
            self.assertFalse(db.verify_parent_pin("0000"))

            # Remove PIN
            db.set_parent_pin(None)
            self.assertIsNone(db.get_parent_pin())
            self.assertTrue(db.verify_parent_pin("any"))
            db.close()
