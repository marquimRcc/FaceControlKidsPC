import unittest
from facekids.session import SessionState, state_from_wts_flags
from facekids.policy import SessionAwarePolicy, Action


class SessionTest(unittest.TestCase):
    def test_locked_session_pause(self):
        p = SessionAwarePolicy()
        remain = {1: 120.0, 2: 120.0}
        self.assertEqual(p.step(0, True, 1, remain).action, Action.WAIT)
        self.assertEqual(p.step(5, True, 1, remain).action, Action.ALLOW)
        self.assertEqual(p.step(10, True, 1, remain).seconds_to_charge, 5)
        self.assertEqual(p.step(15, False, None, remain).action, Action.SESSION_PAUSED)
        self.assertEqual(p.step(3600, False, None, remain).seconds_to_charge, 0)
        self.assertEqual(p.step(3605, True, 1, remain).action, Action.WAIT)
        self.assertEqual(p.step(3610, True, 1, remain).seconds_to_charge, 0)
        self.assertEqual(p.step(3615, True, 1, remain).seconds_to_charge, 5)

    def test_after_unlock_another_child_uses_their_quota(self):
        p = SessionAwarePolicy()
        balances = {1: 0, 2: 7200}
        p.step(0, True, 1, balances)
        self.assertEqual(p.step(5, True, 1, balances).action, Action.LOCK_QUOTA)
        self.assertEqual(p.step(10, False, None, balances).action, Action.SESSION_PAUSED)
        self.assertEqual(p.step(15, True, 2, balances).action, Action.WAIT)
        self.assertEqual(p.step(20, True, 2, balances).action, Action.ALLOW)
        self.assertEqual(p.step(25, True, 2, balances).seconds_to_charge, 5)
        self.assertEqual(p.step(30, True, 1, balances).seconds_to_charge, 0)
        self.assertEqual(p.step(35, True, 1, balances).action, Action.LOCK_QUOTA)

    def test_unknown_wts_state_is_not_active(self):
        self.assertEqual(state_from_wts_flags(0, 0), SessionState.LOCKED)
        self.assertEqual(state_from_wts_flags(0, 1), SessionState.ACTIVE)
        self.assertEqual(state_from_wts_flags(0, -1), SessionState.UNKNOWN)
        self.assertEqual(state_from_wts_flags(4, 1), SessionState.LOCKED)
        self.assertEqual(state_from_wts_flags(4, 0), SessionState.LOCKED)

    def test_unknown_session_does_not_charge(self):
        p = SessionAwarePolicy()
        p.step(0, True, 1, {1: 100})
        p.step(5, True, 1, {1: 100})
        p.step(10, False, None, {1: 100})
        self.assertEqual(p.step(20, False, 1, {1: 100}).seconds_to_charge, 0)
        self.assertEqual(p.step(25, True, 1, {1: 100}).seconds_to_charge, 0)

    def test_no_face_after_unlock_locks_after_grace(self):
        p = SessionAwarePolicy(confirm_frames=2, uncertain_grace_sec=30)
        p.step(0, False, None, {1: 100})
        p.step(10, True, None, {1: 100})
        self.assertEqual(p.step(20, True, None, {1: 100}).action, Action.WAIT)
        self.assertEqual(p.step(41, True, None, {1: 100}).action, Action.LOCK_UNCERTAIN)


if __name__ == "__main__":
    unittest.main()
