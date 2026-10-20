import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

from facekids.parent_face_pilot import (
    Outcome, RecognitionWindow, REQUIRED_SAMPLES,
    _valid_features, replace_templates
)
from facekids.storage import Storage


class ParentFacePilotTests(unittest.TestCase):
    def test_temporal_agreement_and_reset(self):
        check = RecognitionWindow(7)
        self.assertEqual(check.observe(1, 7, 100), Outcome.VERIFYING)
        self.assertEqual(check.observe(1, 7, 101), Outcome.VERIFYING)
        self.assertEqual(check.observe(1, 7, 101.1), Outcome.VERIFIED_DEMO)
        self.assertEqual(check.observe(0, None, 102), Outcome.NO_FACE)
        self.assertEqual(check.observe(1, 7, 102.1), Outcome.VERIFYING)
        self.assertEqual(check.observe(2, 7, 103), Outcome.MANY_FACES)
        self.assertEqual(check.observe(1, 8, 103.1), Outcome.UNKNOWN)
        self.assertEqual(check.observe(1, 7, 104), Outcome.VERIFYING)
        self.assertEqual(check.observe(1, 7, 108), Outcome.VERIFYING)

    def test_invalid_vectors_are_rejected(self):
        vec = np.ones(128, dtype=np.float32)
        self.assertTrue(_valid_features(vec))
        for value in (np.zeros(128), np.ones(127),
                      np.full(128, np.nan), np.full(128, np.inf)):
            self.assertFalse(_valid_features(value))

    def test_atomic_enrollment_replaces_only_adult(self):
        with tempfile.TemporaryDirectory() as root:
            db = Storage(Path(root) / 'adult.sqlite3')
            try:
                adult = db.add_person('Adulto', 120)
                other = db.add_person('Outra pessoa', 120)
                vec = np.ones(128, dtype=np.float32)
                db.add_embedding(other, vec)
                replace_templates(db, adult, [vec] * REQUIRED_SAMPLES)
                self.assertEqual(db.enrollment_count(adult), 12)
                self.assertEqual(db.enrollment_count(other), 1)
                with self.assertRaises(ValueError):
                    replace_templates(db, adult, [vec] * 11)
                self.assertEqual(db.enrollment_count(adult), 12)
                self.assertEqual(db.enrollment_count(other), 1)
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
