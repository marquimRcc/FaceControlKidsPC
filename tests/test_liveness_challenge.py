import unittest
from facekids.liveness_challenge import HeadMotionDiagnostic, Step


class MotionChallengeTests(unittest.TestCase):
    def case(self, direction=1):
        return HeadMotionDiagnostic(session_id=7, start_ms=1000,
                                    direction=direction, last_ms=1000)

    def sample(self, obj, offset, time_ms, face_count=1, session_id=7):
        return obj.observe(session_id=session_id, now_ms=time_ms,
                           face_count=face_count, nose_offset=offset)

    def test_correct_sequence_is_never_real_liveness(self):
        c = self.case()
        self.assertEqual(self.sample(c, 0, 1100), Step.TURN)
        self.assertEqual(self.sample(c, .25, 1400), Step.RECENTER)
        self.assertEqual(self.sample(c, 0, 1700), Step.OBSERVED_NOT_AUTHENTICATED)
        self.assertFalse(c.authenticates_liveness())
        self.assertFalse(c.permits_windows_logon())

    def test_static_photo_never_completes_challenge(self):
        c = self.case()
        for i in range(4):
            self.sample(c, 0, 1100+i*250)
        self.assertEqual(c.step, Step.TURN)
        self.assertFalse(c.permits_windows_logon())

    def test_wrong_direction_and_session_are_denied(self):
        c = self.case(-1)
        self.sample(c, 0, 1100)
        self.assertEqual(self.sample(c, .30, 1300), Step.DENIED)
        x = self.case()
        self.assertEqual(self.sample(x, 0, 1200, session_id=8), Step.DENIED)

    def test_two_faces_nan_and_expired_are_denied(self):
        for offset, count, time in [(0, 2, 1100), (float("nan"),1,1100),
                                    (float("inf"),1,1100), (0,1,9101)]:
            with self.subTest(offset=offset, count=count, time=time):
                self.assertEqual(self.sample(self.case(),offset,time, count),Step.DENIED)

    def test_clock_regression_and_replay_no_second_grant(self):
        c=self.case()
        self.assertEqual(self.sample(c, 0, 1100), Step.TURN)
        self.assertEqual(self.sample(c, .3, 1099), Step.DENIED)
        x=self.case()
        self.sample(x, 0, 1100)
        self.sample(x, .3, 1400)
        self.sample(x, 0, 1700)
        self.assertEqual(self.sample(x, .3, 2000),Step.OBSERVED_NOT_AUTHENTICATED)
        self.assertFalse(x.authenticates_liveness())


if __name__ == "__main__":
    unittest.main()
