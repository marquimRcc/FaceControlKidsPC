import math
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from facekids import linux_pam_helper
from facekids.child_quota_pilot import provision_three_children
from facekids.linux_auth import FaceApproval, FaceApprovalBroker, approval_still_allowed
from facekids.session import SessionState
from facekids.storage import Storage


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

    @patch.dict(
        "os.environ",
        {
            "PAM_TYPE": "auth",
            "PAM_USER": "filhos",
            "FACEKIDS_AUTH_SOCKET": "/tmp/untrusted.sock",
        },
        clear=True,
    )
    @patch("facekids.linux_pam_helper.socket.AF_UNIX", 1, create=True)
    @patch("facekids.linux_pam_helper.socket.socket")
    @patch("facekids.linux_pam_helper.linux_display_session", return_value="4")
    def test_pam_helper_accepts_only_daemon_allow(self, _session, socket_factory):
        client = MagicMock()
        socket_factory.return_value = client
        client.recv.return_value = b"ALLOW\n"
        self.assertEqual(linux_pam_helper.main(), 0)
        client.connect.assert_called_once_with(str(linux_pam_helper.AUTH_SOCKET))
        self.assertNotIn("untrusted", str(linux_pam_helper.AUTH_SOCKET))
        client.sendall.assert_called_once_with(b"AUTH 4\n")
        client.recv.return_value = b"DENY\n"
        self.assertEqual(linux_pam_helper.main(), 1)

    @patch.dict("os.environ", {"PAM_TYPE": "account", "PAM_USER": "filhos"}, clear=True)
    def test_pam_helper_rejects_non_auth_phase(self):
        self.assertEqual(linux_pam_helper.main(), 1)

    def test_nonfinite_clock_and_invalid_identity_are_rejected(self):
        broker = FaceApprovalBroker()
        base = {
            "session_id": "4", "state": SessionState.LOCKED, "child_id": 1,
            "quota_available": True, "curfew_clear": True,
        }
        for now in (math.nan, math.inf, -1):
            self.assertIsNone(broker.observe(now=now, **base))
        self.assertIsNone(broker.observe(now=1, **{**base, "child_id": True}))
        self.assertIsNone(broker.observe(now=1, **{**base, "session_id": "4;bad"}))

    def test_redemption_rechecks_quota_and_curfew(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Storage(Path(directory) / "kids.sqlite3")
            try:
                child = min(provision_three_children(store))
                approval = FaceApproval("4", child, 1)
                today = date.today().isoformat()
                self.assertTrue(approval_still_allowed(store, approval, today))
                store.charge(child, store.remaining(child, today), today)
                self.assertFalse(approval_still_allowed(store, approval, today))
                other = sorted(provision_three_children(store))[1]
                approval = FaceApproval("4", other, 2)
                store.set_curfew_config(True, "00:00", "00:01")
                self.assertFalse(approval_still_allowed(store, approval, today))
            finally:
                store.close()

    def test_database_failure_denies_approval(self):
        store = MagicMock()
        store.is_curfew_active.side_effect = sqlite3.OperationalError("database locked")
        self.assertFalse(
            approval_still_allowed(store, FaceApproval("4", 1, 1), "2026-10-22")
        )


if __name__ == "__main__":
    unittest.main()
