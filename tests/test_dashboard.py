import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from facekids.storage import Storage
from facekids.dashboard import cards_from_storage,time_label
from facekids.admin_auth import hash_pin,verify_pin,AUTH_SETTING

class AdminTests(unittest.TestCase):
    def test_independent_bonus(self):
        with TemporaryDirectory() as folder:
            db=Storage(Path(folder)/"kids.db")
            a=db.add_person("Filho 1",120)
            b=db.add_person("Filho 2",120)
            db.charge(a,1800,"2026-10-19")
            db.add_bonus(a,15,"2026-10-19")
            self.assertEqual(db.remaining(a,"2026-10-19"),6300)
            self.assertEqual(db.remaining(b,"2026-10-19"),7200)
            self.assertEqual(db.remaining(a,"2026-10-20"),7200)
            db.close()

    def test_limit_change_and_missing_user(self):
        with TemporaryDirectory() as folder:
            db=Storage(Path(folder)/"kids.db")
            pid=db.add_person("Filho",120)
            db.set_daily_limit(pid,90)
            self.assertEqual(db.remaining(pid),5400)
            with self.assertRaises(KeyError): db.set_daily_limit(99999,120)
            with self.assertRaises(ValueError): db.add_bonus(pid,-1)
            db.close()

    def test_cards(self):
        with TemporaryDirectory() as folder:
            db=Storage(Path(folder)/"kids.db")
            db.add_person("Filho",120)
            card=cards_from_storage(db)[0]
            self.assertEqual(card.remaining_seconds,7200)
            self.assertEqual(card.samples,0)
            self.assertEqual(time_label(7199),"1h 59min")
            db.close()

    def test_pin_and_persistence(self):
        with TemporaryDirectory() as folder:
            filename=Path(folder)/"kids.db"
            db=Storage(filename)
            db.set_setting(AUTH_SETTING,hash_pin("123456"))
            db.close()
            db=Storage(filename)
            self.assertTrue(verify_pin("123456",db.get_setting(AUTH_SETTING)))
            self.assertFalse(verify_pin("000000",db.get_setting(AUTH_SETTING)))
            self.assertFalse(verify_pin("123456","invalid"))
            db.close()

    def test_bad_pin(self):
        with self.assertRaises(ValueError): hash_pin("abc1")
        with self.assertRaises(ValueError): hash_pin("123")

if __name__=="__main__":
    unittest.main()
