"""Recovery safety: untrusted flags cannot replace Windows SCM/NTFS proof."""
from pathlib import Path
from types import SimpleNamespace
import os
import unittest
from unittest.mock import patch

from facekids import quota_vm_recovery_gate_win as gate


class VmRecoveryPreflightTests(unittest.TestCase):
    def setUp(self):
        self.db = Path("tmp") / "facekids-quota-lab" / "writer-fixture.sqlite3"
        self.models = Path("tmp") / "facekids-quota-lab" / "models"
        self.sid = "S-1-5-21-100-200-300-1001"

    def test_stopped_service_with_matching_paths_and_acl_is_required(self):
        self.assertTrue(gate.require_recovery_preconditions(
            expected_database=self.db,
            configured_database=self.db,
            registered_service_state=gate.SCM_STOPPED,
            acl_is_protected=True,
        ))
        for value in (None, True, 0, 2, 3, 4, 5, 7, 1.0, "1"):
            with self.subTest(state=value), self.assertRaises(PermissionError):
                gate.require_recovery_preconditions(
                    expected_database=self.db,
                    configured_database=self.db,
                    registered_service_state=value,
                    acl_is_protected=True,
                )
        for path in (self.db.with_name("other.sqlite3"), self.db.parent):
            with self.assertRaises(PermissionError):
                gate.require_recovery_preconditions(
                    expected_database=self.db, configured_database=path,
                    registered_service_state=gate.SCM_STOPPED,
                    acl_is_protected=True,
                )
        with self.assertRaises(PermissionError):
            gate.require_recovery_preconditions(
                expected_database=self.db, configured_database=self.db,
                registered_service_state=gate.SCM_STOPPED,
                acl_is_protected=False,
            )

    def test_os_verified_hklm_and_acl_then_scm_before_approval(self):
        with patch.object(gate, "os", SimpleNamespace(name="nt")), \
             patch.object(gate, "read_hklm_writer_vm_config",
                          return_value=(self.db, self.sid, self.models)) as hk, \
             patch.object(gate, "assert_protected_vm_ledger_acl") as acl, \
             patch.object(gate, "query_registered_writer_state",
                          return_value=gate.SCM_STOPPED) as query, \
             patch.object(Path, "resolve", return_value=self.db):
            self.assertTrue(gate.verify_offline_vm_recovery(expected_database=self.db))
            hk.assert_called_once_with()
            acl.assert_called_once_with(self.db, self.models, self.sid)
            query.assert_called_once_with()

    def test_running_service_and_missing_acl_never_attest_offline(self):
        with patch.object(gate, "os", SimpleNamespace(name="nt")), \
             patch.object(gate, "read_hklm_writer_vm_config",
                          return_value=(self.db, self.sid, self.models)), \
             patch.object(gate, "assert_protected_vm_ledger_acl") as acl, \
             patch.object(gate, "query_registered_writer_state",
                          return_value=4), \
             patch.object(Path, "resolve", return_value=self.db):
            with self.assertRaises(PermissionError):
                gate.verify_offline_vm_recovery(expected_database=self.db)
            acl.assert_called_once_with(self.db, self.models, self.sid)
        with patch.object(gate, "os", SimpleNamespace(name="nt")), \
             patch.object(gate, "read_hklm_writer_vm_config",
                          return_value=(self.db, self.sid, self.models)), \
             patch.object(gate, "assert_protected_vm_ledger_acl",
                          side_effect=PermissionError("child can edit models")), \
             patch.object(gate, "query_registered_writer_state") as query, \
             patch.object(Path, "resolve", return_value=self.db):
            with self.assertRaises(PermissionError):
                gate.verify_offline_vm_recovery(expected_database=self.db)
            query.assert_not_called()

    def test_policy_disagreement_rejects_before_scm_check(self):
        with patch.object(gate, "os", SimpleNamespace(name="nt")), \
             patch.object(gate, "read_hklm_writer_vm_config",
                          return_value=(self.db, self.sid, self.models)), \
             patch.object(gate, "assert_protected_vm_ledger_acl") as acl, \
             patch.object(gate, "query_registered_writer_state") as query, \
             patch.object(Path, "resolve", return_value=self.db.with_name("different.db")):
            with self.assertRaises(PermissionError):
                gate.verify_offline_vm_recovery(expected_database=self.db)
            acl.assert_not_called()
            query.assert_not_called()

    @unittest.skipIf(os.name == "nt", "This verifies the non-Windows fail-closed path")
    def test_non_windows_cannot_claim_recovery_is_ready(self):
        with self.assertRaises(RuntimeError):
            gate.verify_offline_vm_recovery(expected_database=self.db)


if __name__ == "__main__":
    unittest.main()
