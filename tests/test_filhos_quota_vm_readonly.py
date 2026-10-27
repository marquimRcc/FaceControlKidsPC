"""Read-only VM agent tests — never touch parent quotas or Windows login."""
import inspect
import unittest
from unittest.mock import MagicMock, patch

from facekids.filhos_quota_vm_readonly import (
    VmLabSnapshot, observe_vm_lab_once,
)
from facekids.quota_broker_transport_win import LAB_PIPE_PREFIX
from facekids.quota_broker_protocol import BROKER_PROTOCOL


SID = "S-1-5-21-1-2-3-1001"
LAB_PIPE = LAB_PIPE_PREFIX + "0123456789abcdef0123456789abcdef"


class VmReadOnlyChildAgentTests(unittest.TestCase):
    def test_authorized_lab_snapshot_uses_only_policy_sid_and_fixed_pipe(self):
        query = MagicMock(return_value={
            "status": "OK", "version": BROKER_PROTOCOL,
            "remaining_seconds": 90, "allowed_now": True,
        })
        result = observe_vm_lab_once(
            trusted_mapping={SID: 1}, actual_token_sid=SID,
            pipe_name=LAB_PIPE, query_lab=query,
        )
        self.assertEqual(result, VmLabSnapshot("observed", 90.0))
        self.assertFalse(result.may_enforce_lock)
        self.assertFalse(result.charged_locally)
        query.assert_called_once_with(LAB_PIPE)

    def test_wrong_sid_refuses_before_opening_any_pipe(self):
        query = MagicMock(side_effect=AssertionError("must not query"))
        for sid in (None, "Filhos", "S-1-5-18", "S-1-5-21-1-2-3-2002"):
            with self.subTest(sid=sid):
                result = observe_vm_lab_once(
                    trusted_mapping={SID: 1},
                    actual_token_sid=sid, pipe_name=LAB_PIPE, query_lab=query,
                )
                self.assertEqual(result.status, "unauthorized")
                self.assertFalse(result.may_enforce_lock)
        query.assert_not_called()

    def test_no_child_controlled_id_in_request(self):
        query = MagicMock(return_value={"status": "DENY"})
        for mapping in ({SID: 1, "S-1-5-21-2-3-4-1001": 2}, {SID: True}, {}, {SID: 0}):
            with self.subTest(mapping=mapping):
                result = observe_vm_lab_once(
                    trusted_mapping=mapping, actual_token_sid=SID,
                    pipe_name=LAB_PIPE, query_lab=query,
                )
                self.assertEqual(result.status, "unauthorized")
        query.assert_not_called()

    def test_invalid_pipe_or_malicious_reply_cannot_trigger_actions(self):
        for pipe in (LAB_PIPE[:-1], LAB_PIPE + "x", LAB_PIPE_PREFIX + "../",
                     r"\\.\pipe\FaceKidsAuthPipe"):
            with self.subTest(pipe=pipe):
                query = MagicMock()
                result = observe_vm_lab_once(
                    trusted_mapping={SID: 1}, actual_token_sid=SID,
                    pipe_name=pipe, query_lab=query,
                )
                self.assertEqual(result.status, "invalid-policy")
                query.assert_not_called()
        observed = observe_vm_lab_once(
            trusted_mapping={SID: 1}, actual_token_sid=SID,
            pipe_name=LAB_PIPE, query_lab=lambda _: {
                "status": "OK", "version": BROKER_PROTOCOL,
                "remaining_seconds": 0, "allowed_now": True,
            },
        )
        self.assertEqual(observed.status, "invalid")
        self.assertFalse(observed.may_enforce_lock)

    def test_vm_probe_source_does_not_access_storage_lock_or_windows_auth(self):
        from facekids import filhos_quota_vm_readonly as probe
        text = inspect.getsource(probe)
        for disallowed in ("Storage(", "charge(", "lock_current_session(",
                           "LockWorkStation(", "last_unlock.json", "win32serviceutil.InstallService("):
            with self.subTest(symbol=disallowed):
                self.assertNotIn(disallowed, text)
        self.assertIn("read_hklm_lab_configuration()", text)
        self.assertIn("effective_windows_sid()", text)

    def test_effective_sid_does_not_fall_back_to_name_on_non_windows(self):
        from facekids.filhos_quota_vm_readonly import effective_windows_sid
        import os
        if os.name != "nt":
            with self.assertRaises(RuntimeError):
                effective_windows_sid()


if __name__ == "__main__":
    unittest.main()
