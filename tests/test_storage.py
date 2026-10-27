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

    def test_charge_rejects_nonfinite_and_invalid_usage_without_mutation(self):
        with TemporaryDirectory() as d:
            db = Storage(Path(d) / "family.sqlite3")
            first = db.add_person("First", 120)
            second = db.add_person("Second", 120)
            day = "2026-10-24"
            db.charge(first, 12.5, day)
            before = db.used(first, day)
            for amount in (float("nan"), float("inf"), -float("inf"), -1,
                           True, "5", None, [], {}):
                with self.subTest(amount=str(amount)), self.assertRaises(ValueError):
                    db.charge(first, amount, day)
                self.assertEqual(db.used(first, day), before)
                self.assertEqual(db.used(second, day), 0)
            for invalid_day in ("2026-02-30", "2026-2-4", "", 123, None):
                # None means "today" by existing contract and is allowed.
                if invalid_day is None:
                    continue
                with self.subTest(day=str(invalid_day)), self.assertRaises(ValueError):
                    db.charge(first, 10, invalid_day)
                self.assertEqual(db.used(first, day), before)
            db.close()

    def test_atomic_capped_debit_respects_quota_and_child_isolation(self):
        with TemporaryDirectory() as d:
            path = Path(d) / "ledger.sqlite3"
            writer = Storage(path)
            second_writer = Storage(path)
            try:
                first = writer.add_person("First", 1)
                second = writer.add_person("Second", 2)
                day = "2026-10-24"
                self.assertEqual(writer.charge_up_to_available(first, 50, day), 50)
                self.assertEqual(second_writer.charge_up_to_available(first, 50, day), 10)
                self.assertEqual(writer.charge_up_to_available(first, 10, day), 0)
                self.assertEqual(second_writer.remaining(first, day), 0)
                self.assertEqual(writer.used(first, day), 60)
                self.assertEqual(writer.remaining(second, day), 120)
                self.assertEqual(second_writer.charge_up_to_available(second, 2.5, day), 2.5)
                self.assertEqual(writer.remaining(second, day), 117.5)
            finally:
                second_writer.close()
                writer.close()

    def test_atomic_debit_rejects_invalid_request_without_side_effects(self):
        with TemporaryDirectory() as d:
            db = Storage(Path(d) / "ledger.sqlite3")
            try:
                cid = db.add_person("Test", 1)
                day = "2026-10-24"
                for seconds in (float("nan"), float("inf"), -1, True, "50", None):
                    with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                        db.charge_up_to_available(cid, seconds, day)
                for invalid_day in ("2026-02-30", "2026-2-4", "", 3):
                    with self.subTest(day=invalid_day), self.assertRaises(ValueError):
                        db.charge_up_to_available(cid, 5, invalid_day)
                with self.assertRaises(KeyError):
                    db.charge_up_to_available(999_999, 5, day)
                self.assertEqual(db.used(cid, day), 0)
            finally:
                db.close()

    def test_service_tick_receipt_blocks_replay_across_connections(self):
        with TemporaryDirectory() as d:
            path = Path(d) / "ledger.sqlite3"
            first_connection = Storage(path)
            second_connection = Storage(path)
            try:
                child = first_connection.add_person("Child", 1)
                day = "2026-10-24"
                first_id = "0123456789abcdef0123456789abcdef"
                second_id = "11111111111111111111111111111111"
                self.assertEqual(first_connection.charge_capped_once(first_id, child, 40, day), 40)
                self.assertEqual(second_connection.charge_capped_once(first_id, child, 40, day), 0)
                with self.assertRaises(ValueError):
                    second_connection.charge_capped_once(first_id, child, 30, day)
                self.assertEqual(second_connection.charge_capped_once(second_id, child, 40, day), 20)
                self.assertEqual(first_connection.remaining(child, day), 0)
                self.assertEqual(first_connection.used(child, day), 60)
                self.assertEqual(first_connection.charge_capped_once(second_id, child, 40, day), 0)
            finally:
                second_connection.close()
                first_connection.close()

    def test_service_tick_rejects_malformed_identity_and_rolls_back(self):
        with TemporaryDirectory() as d:
            db = Storage(Path(d) / "ledger.sqlite3")
            try:
                cid = db.add_person("Child", 1)
                day = "2026-10-24"
                for bad_id in ("", "a" * 31, "A" * 32, "z" * 32, None):
                    with self.subTest(event_id=bad_id), self.assertRaises(ValueError):
                        db.charge_capped_once(bad_id, cid, 10, day)
                good_id = "22222222222222222222222222222222"
                for seconds in (float("nan"), float("inf"), -3, True, "10"):
                    with self.subTest(amount=seconds), self.assertRaises(ValueError):
                        db.charge_capped_once(good_id, cid, seconds, day)
                with self.assertRaises(KeyError):
                    db.charge_capped_once(good_id, 99999, 5, day)
                self.assertEqual(db.charge_capped_once(good_id, cid, 10, day), 10)
                self.assertEqual(db.used(cid, day), 10)
            finally:
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
