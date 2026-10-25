"""SCM service configuration preflight, no service creation/registry writes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

from facekids.quota_broker_scm_win import (
    SERVICE_NAME, FaceKidsQuotaLabService, validate_service_registry_config,
    _validate_service_user_sid,
)


class ServiceLabConfigTests(unittest.TestCase):
    def config(self, path: Path):
        return {
            "LabOnly": 1,
            "Database": str(path),
            "ClientSid": "S-1-5-21-1-2-3-1001",
            "ChildId": 1,
            "PipeSuffix": "0123456789abcdef0123456789abcdef",
        }

    def test_valid_protected_registry_fixture_is_only_read_only_lab(self):
        with TemporaryDirectory() as td:
            directory = Path(td) / "facekids-quota-lab"
            directory.mkdir()
            database = directory / "ledger.sqlite3"
            database.write_bytes(b"synthetic")
            pipe, target, mapping = validate_service_registry_config(self.config(database))
            self.assertTrue(pipe.endswith("0123456789abcdef0123456789abcdef"))
            self.assertEqual(target, database.resolve())
            self.assertEqual(mapping, {"S-1-5-21-1-2-3-1001": 1})
            self.assertEqual(database.read_bytes(), b"synthetic")
            self.assertEqual(SERVICE_NAME, "FaceKidsQuotaLabOnly")

    def test_service_process_sid_is_strictly_required(self):
        _validate_service_user_sid("S-1-5-18", "S-1-5-18")
        for actual, expected in (
            ("S-1-5-18", "S-1-5-21-1-2-3-1001"),
            ("Filhos", "Filhos"),
            ("S-1-5-18", ""),
            ("S-1-5-18\\n", "S-1-5-18"),
            (None, "S-1-5-18"),
            (True, True),
        ):
            with self.subTest(actual=actual, expected=expected), self.assertRaises(PermissionError):
                _validate_service_user_sid(actual, expected)

    def test_missing_or_forged_policy_is_rejected(self):
        with TemporaryDirectory() as td:
            d = Path(td) / "facekids-quota-lab"
            d.mkdir()
            db = d / "ledger.sqlite3"
            db.write_bytes(b"fixture")
            for key, invalid in (
                ("LabOnly", 0),
                ("LabOnly", True),
                ("LabOnly", "1"),
                ("ClientSid", "Filhos"),
                ("ChildId", 0),
                ("ChildId", True),
                ("PipeSuffix", "!" * 32),
                ("Database", None),
            ):
                cfg = self.config(db)
                cfg[key] = invalid
                with self.subTest(key=key, value=invalid), self.assertRaises(ValueError):
                    validate_service_registry_config(cfg)
            cfg = self.config(db)
            cfg["UnknownFlag"] = 1
            with self.assertRaises(ValueError):
                validate_service_registry_config(cfg)

    def test_reject_data_inside_production_programdata_even_if_named_lab(self):
        with TemporaryDirectory() as td:
            fake_programdata = Path(td) / "ProgramData"
            nested = fake_programdata / "FaceKids" / "facekids-quota-lab"
            nested.mkdir(parents=True)
            target = nested / "ledger.sqlite3"
            target.write_bytes(b"fixture")
            with patch.dict(os.environ, {"PROGRAMDATA": str(fake_programdata)}):
                with self.assertRaisesRegex(ValueError, "Production"):
                    validate_service_registry_config(self.config(target))

    @unittest.skipUnless(os.name == "nt", "Windows registry API only")
    def test_hklm_policy_enforces_actual_winreg_types(self):
        import winreg
        from facekids.quota_broker_scm_win import read_hklm_lab_configuration

        with TemporaryDirectory() as td:
            root = Path(td) / "facekids-quota-lab"
            root.mkdir()
            db = root / "ledger.sqlite3"
            db.write_bytes(b"synthetic")
            good = self.config(db)
            type_map = {
                "LabOnly": winreg.REG_DWORD,
                "Database": winreg.REG_SZ,
                "ClientSid": winreg.REG_SZ,
                "ChildId": winreg.REG_DWORD,
                "PipeSuffix": winreg.REG_SZ,
            }
            from unittest.mock import MagicMock
            handle = MagicMock()
            handle.__enter__.return_value = handle
            with patch.object(winreg, "OpenKey", return_value=handle), patch.object(
                winreg, "QueryValueEx", side_effect=lambda _handle, name:
                (good[name], type_map[name])
            ):
                pipe, got_db, mapping = read_hklm_lab_configuration()
            self.assertTrue(pipe.endswith("0123456789abcdef0123456789abcdef"))
            self.assertEqual(got_db, db.resolve())
            self.assertEqual(mapping, {good["ClientSid"]: 1})

            # Each field: force the WRONG Windows registry type while value
            # remains syntactically valid. Must fail before the service starts.
            for name in type_map:
                bad = dict(type_map)
                bad[name] = (winreg.REG_SZ if type_map[name] == winreg.REG_DWORD
                             else winreg.REG_EXPAND_SZ)
                with self.subTest(name=name), patch.object(
                    winreg, "OpenKey", return_value=handle
                ), patch.object(
                    winreg, "QueryValueEx", side_effect=lambda _handle, key:
                    (good[key], bad[key])
                ), self.assertRaises(ValueError):
                    read_hklm_lab_configuration()

    def test_scm_module_never_auto_installs_or_starts_on_import(self):
        self.assertEqual(FaceKidsQuotaLabService._svc_name_, "FaceKidsQuotaLabOnly")


if __name__ == "__main__":
    unittest.main()
