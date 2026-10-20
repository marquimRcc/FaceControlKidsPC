import unittest

from facekids.windows_session_diagnostic import (
    LockView, SessionObservation, classify, summarize,
)


class WindowsSessionDiagnosticTests(unittest.TestCase):
    def test_locked_only_for_active_session(self):
        self.assertIs(classify(0, 0), LockView.LOCKED)

    def test_unlocked_only_for_active_session(self):
        self.assertIs(classify(0, 1), LockView.UNLOCKED)

    def test_unknown_for_unrecognized_flags(self):
        for flag in (-1, 2, 255, None):
            self.assertIs(classify(0, flag), LockView.UNKNOWN)

    def test_disconnected_session_is_not_eligible(self):
        for connect_state in (1, 2, 4, 5, 6, 7, 8, 9):
            self.assertIs(classify(connect_state, 0), LockView.INACTIVE)

    def test_invalid_state_is_unknown(self):
        self.assertIs(classify("0", 0), LockView.UNKNOWN)
        self.assertIs(classify(None, 0), LockView.UNKNOWN)

    def test_summary_finds_target_but_does_not_authorize(self):
        result = summarize([
            SessionObservation(1, "MarcosMiniPC", LockView.UNLOCKED),
            SessionObservation(2, "Filhos", LockView.LOCKED),
            SessionObservation(3, "FILHOS", LockView.INACTIVE),
        ])
        self.assertEqual(result, {
            "sessions": 3, "target_present": True,
            "target_locked": 1, "target_inactive": 1, "target_unknown": 0,
        })

    def test_no_target_session_is_normal(self):
        result = summarize([SessionObservation(1, "MarcosMiniPC", LockView.UNLOCKED)])
        self.assertFalse(result["target_present"])
        self.assertEqual(result["target_locked"], 0)


if __name__ == "__main__":
    unittest.main()
