import unittest
from unittest.mock import MagicMock, patch

from facekids import linux_pam_helper
from facekids.linux_auth import FaceApprovalBroker
from facekids.session import SessionState


class LinuxAuthTests(unittest.TestCase):
    def test_three_locked_observations_issue_one_use_ticket(self):
        broker = FaceApprovalBroker(confirmations=3, ttl_seconds=10)
        arguments = {
            "session_id": "4", "state": SessionState.LOCKED, "child_id": 2,
            "quota_available": True, "curfew_clear": True,
        }
        self.assertIsNone(broker.observe(now=1, **arguments))
        self.assertIsNone(broker.observe(now=2, **arguments))
        approval = broker.observe(now=3, **arguments)
        self.assertEqual(approval.child_id, 2)
        self.assertEqual(broker.consume("4", 4).child_id, 2)
        self.assertIsNone(broker.consume("4", 4.1))

    def test_ticket_is_bound_fresh_and_fail_closed(self):
        cases = (
            {"state": SessionState.ACTIVE},
            {"child_id": None},
            {"quota_available": False},
            {"curfew_clear": False},
            {"session_id": None},
        )
        base = {
            "session_id": "4", "state": SessionState.LOCKED, "child_id": 1,
            "quota_available": True, "curfew_clear": True,
        }
        for changed in cases:
            broker = FaceApprovalBroker()
            values = {**base, **changed}
            for now in (1, 2, 3):
                self.assertIsNone(broker.observe(now=now, **values))
        broker = FaceApprovalBroker()
        for now in (1, 2, 3):
            broker.observe(now=now, **base)
        self.assertIsNone(broker.consume("different", 4))
        self.assertIsNone(broker.consume("4", 4))
        for now in (5, 6, 7):
            broker.observe(now=now, **base)
        self.assertIsNone(broker.consume("4", 18))

    def test_switch_and_time_gap_restart_confirmation(self):
        broker = FaceApprovalBroker()
        base = {
            "session_id": "4", "state": SessionState.LOCKED,
            "quota_available": True, "curfew_clear": True,
        }
        broker.observe(now=1, child_id=1, **base)
        broker.observe(now=2, child_id=2, **base)
        self.assertIsNone(broker.observe(now=3, child_id=2, **base))
        self.assertIsNotNone(broker.observe(now=4, child_id=2, **base))
        broker.reset()
        broker.observe(now=10, child_id=1, **base)
        broker.observe(now=20, child_id=1, **base)
        self.assertIsNone(broker.observe(now=21, child_id=1, **base))

    @patch.dict("os.environ", {"PAM_TYPE": "auth", "PAM_USER": "filhos"}, clear=True)
    @patch("facekids.linux_pam_helper.socket.socket")
    @patch("facekids.linux_pam_helper.linux_display_session", return_value="4")
    def test_pam_helper_accepts_only_daemon_allow(self, _session, socket_factory):
        client = MagicMock()
        socket_factory.return_value = client
        client.recv.return_value = b"ALLOW\n"
        self.assertEqual(linux_pam_helper.main(), 0)
        client.sendall.assert_called_once_with(b"AUTH 4\n")
        client.recv.return_value = b"DENY\n"
        self.assertEqual(linux_pam_helper.main(), 1)

    @patch.dict("os.environ", {"PAM_TYPE": "account", "PAM_USER": "filhos"}, clear=True)
    def test_pam_helper_rejects_non_auth_phase(self):
        self.assertEqual(linux_pam_helper.main(), 1)


if __name__ == "__main__":
    unittest.main()
