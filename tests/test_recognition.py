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


if __name__ == "__main__":
    unittest.main()
