"""Strict configuration and SCM lifecycle for VM-only quota writer."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import threading
import unittest
from unittest.mock import MagicMock, patch

from facekids.quota_broker_writer_scm_win import (
    LAB_MARKER_KEY, LAB_MARKER_VALUE, VM_WRITER_SERVICE_NAME,
    VM_WRITER_REGISTRY_PATH, FaceKidsQuotaWriterVmService,
    validate_vm_writer_config,
)
from facekids.storage import Storage


class WriterVmConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="facekids-vm-writer-config-")
        root = Path(self.tmp.name) / "facekids-quota-lab"
        root.mkdir()
        self.db = root / "writer-fixture.sqlite3"
        self.models = root / "models"
        self.models.mkdir()
        self.store = Storage(self.db)
        self.store.add_person("Synthetic child", 2)
        self.store.set_setting(LAB_MARKER_KEY, LAB_MARKER_VALUE)
        self.store.close()
        self.config = {
            "VmLabOnly": 1, "WriterEnabled": 1,
            "Database": str(self.db), "Models": str(self.models),
            "ChildSid": "S-1-5-21-10-20-30-1001",
            "ServiceSid": "S-1-5-18",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_config_rejects_family_files_and_altered_policy(self):
        self.assertEqual(validate_vm_writer_config(self.config),
                         (self.db.resolve(), self.config["ChildSid"], self.models.resolve()))
        for key, bad in [
            ("VmLabOnly", 0), ("WriterEnabled", False),
            ("ServiceSid", "S-1-5-21-10-20-30-1001"),
            ("ChildSid", "Filhos"), ("ChildSid", "S-1-5-18"),
            ("Models", str(self.db)), ("Database", str(self.models)),
        ]:
            with self.subTest(key=key, bad=bad):
                invalid = dict(self.config, **{key: bad})
                with self.assertRaises((ValueError, PermissionError, OSError)):
                    validate_vm_writer_config(invalid)
        unrecognized = dict(self.config, ClientCanCharge=1)
        with self.assertRaises(ValueError):
            validate_vm_writer_config(unrecognized)
        self.assertEqual(VM_WRITER_SERVICE_NAME, "FaceKidsQuotaWriterVmOnly")

    def test_unmarked_or_non_sqlite_fixture_fails_closed(self):
        with sqlite3.connect(self.db) as db:
            db.execute("DELETE FROM settings WHERE key=?", (LAB_MARKER_KEY,))
        with self.assertRaises(PermissionError):
            validate_vm_writer_config(self.config)
        self.db.write_bytes(b"not a database")
        with self.assertRaises(ValueError):
            validate_vm_writer_config(self.config)

    def test_no_file_or_biometrics_deleted_on_denial(self):
        before = self.db.stat().st_size
        bad = dict(self.config, WriterEnabled=0)
        with self.assertRaises(PermissionError):
            validate_vm_writer_config(bad)
        self.assertEqual(self.db.stat().st_size, before)

    def test_service_class_never_auto_registers(self):
        self.assertEqual(FaceKidsQuotaWriterVmService._svc_name_, VM_WRITER_SERVICE_NAME)


@unittest.skipUnless(os.name == "nt", "pywin32 lifecycle applies to Windows")
class WriterVmScmLifecycleTests(unittest.TestCase):
    def setUp(self):
        from facekids import quota_broker_writer_scm_win as service_mod
        if service_mod._ServiceBase is object:
            self.skipTest("pywin32 not installed")
        self.mod = service_mod

    def fake(self):
        instance = object.__new__(self.mod.FaceKidsQuotaWriterVmService)
        instance._stop_signal = threading.Event()
        instance._host = None
        status = []
        instance.ReportServiceStatus = lambda value: status.append(value)
        return instance, status

    def test_real_scm_bridge_uses_only_verified_service_components(self):
        instance, status = self.fake()
        events = []
        class Host:
            def __init__(self, runtime, *, stop_event):
                self.runtime = runtime
                self.stop_event = stop_event

            def on_scm_session_change(self, code, payload):
                events.append((code, payload))

            def run(self):
                self.on_scm_session_change(8, (23,))
                events.append(("ran", self.runtime))

            def request_stop(self):
                events.append("stopped")

        with patch.object(self.mod, "_require_expected_service_sid") as token, \
             patch.object(self.mod, "read_hklm_writer_vm_config",
                          return_value=(Path("synthetic.sqlite3"), "S-1-5-21-1-2-3-1001", Path("models"))) as config, \
             patch.object(self.mod, "assert_protected_vm_ledger_acl") as acl, \
             patch.object(self.mod, "Storage") as storage, \
             patch.object(self.mod, "FaceAuthenticator") as camera, \
             patch.object(self.mod.ServiceOwnedQuotaRuntime,
                          "from_service_authenticator", return_value=object()) as factory, \
             patch.object(self.mod, "ServiceOwnedScmHost", Host):
            instance.SvcDoRun()
            token.assert_called_once_with(registry_path=VM_WRITER_REGISTRY_PATH)
            config.assert_called_once()
            acl.assert_called_once()
            factory.assert_called_once()
            self.assertIn(("ran", factory.return_value), events)
            storage.return_value.close.assert_called_once()
            self.assertIn(self.mod.win32service.SERVICE_RUNNING, status)
            instance.SvcStop()
            self.assertTrue(instance._stop_signal.is_set())

    def test_unlock_and_lock_notifications_are_forwarded_from_scm(self):
        instance, _ = self.fake()
        instance._host = MagicMock()
        with patch.object(self.mod, "servicemanager") as logger:
            instance.SvcOtherEx(self.mod.win32service.SERVICE_CONTROL_SESSIONCHANGE, 8, (23,))
            instance.SvcOtherEx(self.mod.win32service.SERVICE_CONTROL_SESSIONCHANGE, 7, (23,))
        self.assertEqual(instance._host.on_scm_session_change.call_count, 2)
        instance._host.on_scm_session_change.assert_any_call(7, (23,))

    def test_wrong_service_principal_blocks_sqlite_access(self):
        instance, status = self.fake()
        with patch.object(self.mod, "_require_expected_service_sid",
                          side_effect=PermissionError("bad")), \
             patch.object(self.mod, "read_hklm_writer_vm_config") as config, \
             patch.object(self.mod, "Storage") as storage, \
             patch.object(self.mod, "servicemanager"):
            with self.assertRaises(PermissionError):
                instance.SvcDoRun()
        config.assert_not_called()
        storage.assert_not_called()
        self.assertNotIn(self.mod.win32service.SERVICE_RUNNING, status)


if __name__ == "__main__":
    unittest.main()
