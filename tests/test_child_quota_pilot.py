import tempfile
import unittest
from pathlib import Path

from facekids.child_quota_pilot import (
    ChildQuotaEngine, CHILD_LABELS, LIMIT_MINUTES,
    PilotEvent, provision_three_children
)
from facekids.session import SessionState
from facekids.storage import Storage


class ChildQuotaPilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "kids.sqlite3")
        self.engine = ChildQuotaEngine(self.store)
        self.ids = {name: pid for pid, name in self.engine.people.items()}
        self.a = self.ids[CHILD_LABELS[0]]
        self.b = self.ids[CHILD_LABELS[1]]
        self.day = "2026-10-20"

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def step(self, second, identity, session=SessionState.ACTIVE, day=None):
        return self.engine.step(second, day or self.day, session, identity)

    def test_provision_idempotent_and_exactly_three_profiles(self):
        self.assertEqual(len(self.store.people()), 3)
        provision_three_children(self.store)
        self.assertEqual(len(self.store.people()), 3)
        for p in self.store.people():
            self.assertEqual(p[2], LIMIT_MINUTES * 60)

    def test_partial_profile_creation_can_recover(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Storage(Path(folder) / "partial.sqlite3")
            try:
                db.add_person(CHILD_LABELS[0], LIMIT_MINUTES)
                mapping=provision_three_children(db)
                self.assertEqual(len(mapping),3)
                self.assertEqual(len(db.people()),3)
            finally:
                db.close()

    def test_count_after_three_confirmations_without_charge_during_detection(self):
        self.assertEqual(self.step(0, self.a).event, PilotEvent.WAIT)
        self.assertEqual(self.step(1, self.a).event, PilotEvent.WAIT)
        self.assertEqual(self.step(2, self.a).event, PilotEvent.COUNTING)
        self.assertEqual(self.step(3, self.a).charged_seconds, 1)
        self.assertEqual(self.store.remaining(self.a, self.day), 7199)
        self.assertEqual(self.store.remaining(self.b, self.day), 7200)

    def test_switch_kids_never_debits_previous_child(self):
        for t in (0, 1, 2, 3):
            self.step(t, self.a)
        self.step(4, self.b)
        self.step(5, self.b)
        self.step(6, self.b)
        self.assertEqual(self.step(7, self.b).charged_seconds, 1)
        self.assertEqual(self.store.used(self.a, self.day), 1)
        self.assertEqual(self.store.used(self.b, self.day), 1)

    def test_locked_session_pauses_and_requires_reidentification(self):
        for t in (0, 1, 2, 3):
            self.step(t, self.a)
        self.assertEqual(self.step(4, self.a, SessionState.LOCKED).event, PilotEvent.PAUSED)
        self.assertEqual(self.step(5, self.a).event, PilotEvent.WAIT)
        self.step(6, self.a)
        self.assertEqual(self.step(7, self.a).event, PilotEvent.COUNTING)
        self.assertEqual(self.store.used(self.a, self.day), 1)

    def test_date_change_discards_pending_second_and_reidentifies(self):
        for t in (0, 1, 2, 3):
            self.step(t, self.a)
        self.assertEqual(self.step(4, self.a, day="2026-10-21").event, PilotEvent.NEW_DAY)
        self.assertEqual(self.step(5, self.a, day="2026-10-21").event, PilotEvent.WAIT)
        self.assertEqual(self.store.used(self.a, self.day), 1)
        self.assertEqual(self.store.used(self.a, "2026-10-21"), 0)

    def test_unknown_does_not_lock_but_does_not_charge(self):
        self.step(0, None)
        self.assertEqual(self.step(31, None).event, PilotEvent.UNCERTAIN)
        self.assertEqual(self.store.used(self.a, self.day), 0)
        self.assertEqual(self.store.used(self.b, self.day), 0)

    def test_exhaustion_requests_lock_candidate_only(self):
        self.store.charge(self.a, 7199, self.day)
        for t in (0, 1, 2):
            self.step(t, self.a)
        result = self.step(3, self.a)
        self.assertEqual(result.event, PilotEvent.QUOTA_EXHAUSTED)
        self.assertTrue(result.lock_candidate)
        self.assertEqual(result.remaining_seconds, 0)
        self.assertEqual(self.store.used(self.a, self.day), 7200)
        self.assertEqual(self.store.remaining(self.b, self.day), 7200)

    def test_invalid_day_and_clock_rejected(self):
        for invalid in ("2026-02-30", "2026-2-1", ""):
            with self.assertRaises(ValueError):
                self.engine.step(1, invalid, SessionState.ACTIVE, self.a)
        with self.assertRaises(ValueError):
            self.engine.step(float("inf"), self.day, SessionState.ACTIVE, self.a)

    def test_unrelated_people_database_refused(self):
        with tempfile.TemporaryDirectory() as p:
            db = Storage(Path(p) / "separate.sqlite3")
            try:
                db.add_person("Responsavel - Teste", 120)
                with self.assertRaises(ValueError):
                    ChildQuotaEngine(db)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
