import unittest
import numpy as np
from facekids.recognition import Recognizer


class RecognitionTest(unittest.TestCase):
    def test_best_identity_only_when_confident(self):
        a = np.zeros(128, dtype=np.float32)
        b = np.zeros(128, dtype=np.float32)
        a[0] = 1
        b[1] = 1
        self.assertEqual(Recognizer.identify(a, [(1, a), (2, b)])[0], 1)
        self.assertEqual(Recognizer.identify(b, [(1, a), (2, b)])[0], 2)

    def test_unrecognized_and_ambiguous_do_not_match(self):
        a = np.zeros(128, dtype=np.float32)
        b = np.zeros(128, dtype=np.float32)
        a[0] = 1
        b[1] = 1
        c = np.zeros(128, dtype=np.float32)
        c[2] = 1
        self.assertIsNone(Recognizer.identify(c, [(1, a), (2, b)])[0])
        self.assertIsNone(Recognizer.identify(a, [(1, a), (2, a.copy())])[0])

    def test_nonfinite_probe_cannot_match_a_child(self):
        reference = np.zeros(128, dtype=np.float32)
        reference[0] = 1
        for poison in (np.nan, np.inf, -np.inf):
            probe = reference.copy()
            probe[0] = poison
            with self.subTest(value=str(poison)):
                self.assertEqual(Recognizer.identify(probe, [(1, reference)]), (None, None))

    def test_nonfinite_enrollment_is_skipped(self):
        reference = np.zeros(128, dtype=np.float32)
        reference[0] = 1
        bad = reference.copy()
        bad[0] = np.nan
        self.assertEqual(Recognizer.identify(reference, [(2, bad), (1, reference)])[0], 1)
        self.assertEqual(Recognizer.identify(reference, [(2, bad)]), (None, None))

    def test_invalid_dimensions_and_zero_vectors_denied(self):
        vec = np.zeros(128, dtype=np.float32)
        ref = vec.copy()
        ref[0] = 1
        for invalid in (vec, vec[:127], np.array([], dtype=np.float32)):
            with self.subTest(size=invalid.size):
                self.assertEqual(Recognizer.identify(invalid, [(1, ref)]), (None, None))
        self.assertEqual(Recognizer.identify(ref, [(1, np.zeros(128))]), (None, None))



if __name__ == "__main__":
    unittest.main()
