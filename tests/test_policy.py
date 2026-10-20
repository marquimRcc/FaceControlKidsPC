import unittest
from facekids.policy import Policy,Action

class PolicyTest(unittest.TestCase):
    def test_confirm_then_charge_and_lock_quota(self):
        p=Policy(confirm_frames=2,uncertain_grace_sec=30)
        self.assertEqual(p.step(0,1,{1:6}).action,Action.WAIT)
        self.assertEqual(p.step(5,1,{1:6}).action,Action.ALLOW)
        self.assertEqual(p.step(10,1,{1:6}).seconds_to_charge,5)
        decision=p.step(15,1,{1:1})
        self.assertEqual(decision.action,Action.LOCK_QUOTA)
        self.assertEqual(decision.seconds_to_charge,1)
        self.assertEqual(p.step(20,1,{1:0}).action,Action.LOCK_QUOTA)

    def test_unknown_pauses_then_locks(self):
        p=Policy(confirm_frames=2,uncertain_grace_sec=12)
        p.step(0,1,{1:100})
        p.step(5,1,{1:100})
        self.assertEqual(p.step(10,None,{1:100}).action,Action.WAIT)
        self.assertEqual(p.step(25,None,{1:100}).action,Action.LOCK_UNCERTAIN)

    def test_child_change_does_not_charge_wrong_child(self):
        p=Policy()
        p.step(0,1,{1:100,2:100})
        p.step(5,1,{1:100,2:100})
        self.assertEqual(p.step(10,2,{1:100,2:100}).action,Action.WAIT)
        self.assertEqual(p.step(15,2,{1:100,2:100}).seconds_to_charge,0)
        self.assertEqual(p.step(20,2,{1:100,2:100}).seconds_to_charge,5)

    def test_hibernation_no_charge_large_gap(self):
        p=Policy(confirm_frames=1)
        p.step(0,1,{1:10000})
        self.assertEqual(p.step(3600,1,{1:10000}).seconds_to_charge,0)
