"""Deterministic main behavior, including adversarial candidate metadata."""
import unittest
from facekids.session_transition_policy import decide_child_transition as decide
from facekids.session_transition_policy import TransitionDecision as D


class SessionTransitionTests(unittest.TestCase):
    def choice(self, current, ids, faces, idle, candidate, age=0):
        return decide(current, ids, faces, idle, candidate, observation_age_seconds=age)

    def test_main_four_rules_and_unassigned_login(self):
        cases = [
            (1, [1, 2], 2, 25, 2, D.KEEP_CURRENT),
            (1, [2], 1, 14.999, 2, D.KEEP_CURRENT),
            (1, [2], 2, 25, 2, D.SUPPRESS_MULTIPLE_FACES),
            (1, [2], 1, 15, 2, D.SWITCH_CHILD),
            (None, [2], 1, 0, 2, D.SWITCH_CHILD),
            (None, [2], 2, 40, 2, D.SUPPRESS_MULTIPLE_FACES),
            (2, [2], 1, 25, 2, D.KEEP_CURRENT),
        ]
        for current, ids, faces, idle, candidate, wanted in cases:
            with self.subTest(current=current, ids=ids, faces=faces, idle=idle):
                self.assertEqual(self.choice(current, ids, faces, idle, candidate), wanted)

    def test_invalid_metadata_never_switches(self):
        invalid = [
            (1, [2], 1, 16, 3, 0),
            (1, [2], 0, 16, 2, 0),
            (1, [2, 3], 1, 16, 2, 0),
            (1, [2, 2], 2, 16, 2, 0),
            (1, [True], 1, 16, True, 0),
            (1, [2], 1, float('nan'), 2, 0),
            (1, [2], 1, 16, 2, 15.01),
            (1, [2], 1, 16, 2, -1),
            (0, [2], 1, 16, 2, 0),
            (1, "2", 1, 16, 2, 0),
        ]
        for args in invalid:
            with self.subTest(args=args):
                self.assertEqual(self.choice(*args), D.INVALID_OBSERVATION)


if __name__ == "__main__":
    unittest.main()
