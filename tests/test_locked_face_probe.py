from pathlib import Path
import tempfile
import unittest

import numpy as np

from facekids.parent_face_pilot import PROFILE_NAME, REQUIRED_SAMPLES
from facekids.storage import Storage
from facekids.windows_session_diagnostic import LockView as WTS
from facekids.locked_face_probe import (
    LockedFaceStats, Status, load_adult_templates_read_only,
)


class LockedFaceProbeTests(unittest.TestCase):
    def test_three_matching_locked_samples_are_observations_only(self):
        stats = LockedFaceStats(12)
        for at in (1, 2, 3):
            stats.record(WTS.LOCKED, WTS.LOCKED, frame_ok=True,
                         face_count=1, candidate_id=12, now=at)
        self.assertEqual(stats.matching_frames, 3)
        self.assertEqual(stats.confirmation_windows, 1)
        for at in (4, 5):
            stats.record(WTS.LOCKED, WTS.LOCKED, frame_ok=True, now=at)
        self.assertEqual(stats.status(), Status.MATCH_DIAGNOSTIC)

    def test_unlock_transitions_never_count(self):
        stats = LockedFaceStats(12)
        for at in range(20):
            stats.record(WTS.UNLOCKED, WTS.LOCKED, frame_ok=True,
                         face_count=1, candidate_id=12, now=at)
        self.assertEqual(stats.locked_frames, 0)
        self.assertEqual(stats.status(), Status.NOT_ENOUGH_LOCKED_SAMPLES)

    def test_unknown_or_another_id_breaks_streak(self):
        s = LockedFaceStats(9)
        for at in (1, 2):
            s.record(WTS.LOCKED, WTS.LOCKED, frame_ok=True,
                     face_count=1, candidate_id=9, now=at)
        s.record(WTS.UNKNOWN, WTS.LOCKED, frame_ok=True,
                 face_count=1, candidate_id=9, now=3)
        s.record(WTS.LOCKED, WTS.LOCKED, frame_ok=True,
                 face_count=1, candidate_id=9, now=4)
        s.record(WTS.LOCKED, WTS.LOCKED, frame_ok=True,
                 face_count=1, candidate_id=8, now=5)
        self.assertEqual(s.confirmation_windows, 0)
        self.assertEqual(s.unknown_samples, 1)

    def test_time_gap_and_multiple_faces_reset(self):
        s = LockedFaceStats(3)
        for t in (1, 2, 10, 11):
            s.record(WTS.LOCKED, WTS.LOCKED, frame_ok=True,
                     face_count=1, candidate_id=3, now=t)
        self.assertEqual(s.confirmation_windows, 0)
        s.record(WTS.LOCKED, WTS.LOCKED, frame_ok=True,
                 face_count=2, candidate_id=3, now=12)
        self.assertEqual(s.consecutive, 0)
        for t in (13, 14, 15):
            s.record(WTS.LOCKED, WTS.LOCKED, frame_ok=True,
                     face_count=1, candidate_id=3, now=t)
        self.assertEqual(s.confirmation_windows, 1)

    def test_no_match_is_not_success(self):
        s = LockedFaceStats(1)
        for at in range(10):
            s.record(WTS.LOCKED, WTS.LOCKED, frame_ok=True,
                     face_count=1, candidate_id=None, now=at)
        self.assertEqual(s.status(), Status.NO_MATCH)

    def test_readonly_adult_templates_do_not_modify_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pilot.sqlite3"
            db = Storage(path)
            try:
                person = db.add_person(PROFILE_NAME, 120)
                db.add_person("irrelevant", 120)
                for _ in range(REQUIRED_SAMPLES):
                    v = np.zeros(128, dtype=np.float32)
                    v[0] = 1.0
                    db.add_embedding(person, v)
            finally:
                db.close()
            before = path.stat().st_size
            adult_id, templates = load_adult_templates_read_only(path)
            self.assertEqual(adult_id, person)
            self.assertEqual(len(templates), REQUIRED_SAMPLES)
            self.assertEqual(before, path.stat().st_size)
            self.assertFalse((Path(folder) / "new_file.sqlite3").exists())

    def test_invalid_or_missing_database_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                load_adult_templates_read_only(Path(folder) / "missing.sqlite3")
            path = Path(folder) / "pilot.sqlite3"
            db = Storage(path)
            try:
                db.add_person(PROFILE_NAME, 120)
            finally:
                db.close()
            with self.assertRaises(ValueError):
                load_adult_templates_read_only(path)


if __name__ == "__main__":
    unittest.main()
