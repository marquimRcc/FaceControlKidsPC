"""VM bootstrap must use isolated data and reject incomplete opt-ins."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from safepckids.vm_lab_paths import vm_lab_root
from safepckids.platform_paths import application_data_dir
from safepckids.children_pilot import child_pilot_database
from safepckids.storage import default_data_path


class VmLabPathTests(unittest.TestCase):
    def test_no_optin_preserves_existing_default(self):
        # Keep Windows HOMEDRIVE/HOMEPATH/LOCALAPPDATA intact; removing them
        # breaks pathlib's user-home lookup independently of VM isolation.
        with patch.dict(os.environ, {
            "SAFEPCKIDS_VM_LAB_DIR": "", "SAFEPCKIDS_VM_LAB_ACK": ""}):
            self.assertIsNone(vm_lab_root())
            self.assertNotIn("dados-isolados", str(child_pilot_database()))

    def test_optin_routes_both_database_and_avatar_data(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "SafePCKids-VM-Lab" / "dados-isolados"
            env = {"LOCALAPPDATA": td,
                   "SAFEPCKIDS_VM_LAB_DIR": str(root),
                   "SAFEPCKIDS_VM_LAB_ACK": "ISOLATED_VM_ONLY"}
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(vm_lab_root(), root.resolve())
                self.assertEqual(
                    child_pilot_database(), root.resolve() / "data" / "criancas.sqlite3")
                self.assertEqual(
                    default_data_path(), root.resolve() / "data" / "criancas.sqlite3")
                self.assertEqual(application_data_dir(), root.resolve() / "appdata")

    def test_auth_logs_and_unlock_metadata_stay_inside_vm_workspace(self):
        from safepckids.auth_service import authentication_log_dir, unlock_metadata_path
        with TemporaryDirectory() as td:
            root = Path(td) / "SafePCKids-VM-Lab" / "dados-isolados"
            env = {"LOCALAPPDATA": td,
                   "SAFEPCKIDS_VM_LAB_DIR": str(root),
                   "SAFEPCKIDS_VM_LAB_ACK": "ISOLATED_VM_ONLY"}
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(authentication_log_dir(),
                                 root.resolve() / "appdata")
                self.assertEqual(unlock_metadata_path(),
                                 root.resolve() / "appdata" / "last_unlock.json")

    def test_refuses_missing_ack_or_escape_outside_local_appdata(self):
        with TemporaryDirectory() as td:
            with patch.dict(os.environ, {
                "LOCALAPPDATA": td,
                "SAFEPCKIDS_VM_LAB_DIR": str(Path(td) / "SafePCKids-VM-Lab"),
                "SAFEPCKIDS_VM_LAB_ACK": "wrong"}, clear=True):
                with self.assertRaises(RuntimeError):
                    vm_lab_root()
            with patch.dict(os.environ, {
                "LOCALAPPDATA": td,
                "SAFEPCKIDS_VM_LAB_DIR": str(Path(td).parent / "SafePCKids-VM-Lab"),
                "SAFEPCKIDS_VM_LAB_ACK": "ISOLATED_VM_ONLY"}, clear=True):
                with self.assertRaises(RuntimeError):
                    vm_lab_root()


if __name__ == "__main__":
    unittest.main()
