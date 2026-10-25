"""VM child must be read-only, ignore forged server data and never lock."""
import inspect
import os
import unittest
from unittest.mock import Mock, patch

from facekids.filhos_bound_vm_agent import (
    VmBoundChildObserver, VmBoundStatus, observe_vm_bound_once,
    require_vm_bound_policy,
)
from facekids.quota_broker_bound_protocol import BoundBalance


class BoundVmAgentTests(unittest.TestCase):
    def test_one_child_from_service_only_no_charge_or_lock(self):
        for child in (1, 2, 3):
            observer = VmBoundChildObserver(lambda child=child: BoundBalance(
                child, 75, True
            ))
            result = observer.observe()
            self.assertEqual(result, VmBoundStatus("observed", child, 75.0))
            self.assertFalse(result.may_enforce_lock)
            self.assertFalse(result.charged_locally)

    def test_no_face_lease_and_bad_response_fail_closed(self):
        for value in (None, {"child_id": 1}, False, 0, "ALLOW"):
            with self.subTest(value=value):
                observed = VmBoundChildObserver(lambda value=value: value).observe()
                self.assertIn(observed.state, {"invalid", "unverified"})
                self.assertIsNone(observed.child_id)
                self.assertFalse(observed.may_enforce_lock)
        for exception in (OSError(), PermissionError(), TimeoutError(), ValueError(), TypeError()):
            with self.subTest(exception=exception):
                def fail():
                    raise exception
                self.assertEqual(VmBoundChildObserver(fail).observe().state,
                                 "unavailable")

    def test_no_sqlite_open_billing_winlogon_or_env_override_in_agent(self):
        import facekids.filhos_bound_vm_agent as agent
        source = inspect.getsource(agent)
        for disallowed in (
            "Storage(", "sqlite3.connect(", "LockWorkStation(",
            "lock_current_session(", "charge_capped_once(", "charge(",
            "os.environ.get(", "last_unlock.json",
        ):
            self.assertNotIn(disallowed, source)
        self.assertIn('winreg.HKEY_LOCAL_MACHINE', source)
        self.assertIn('query_current_bound_vm_balance', source)

    def test_windows_only_policy_enforced_before_pipe_read(self):
        if os.name != "nt":
            with self.assertRaises(RuntimeError):
                require_vm_bound_policy(actual_windows_sid="S-1-5-21-1-2-3-1001")
            with self.assertRaises(RuntimeError):
                observe_vm_bound_once()


if __name__ == "__main__":
    unittest.main()
