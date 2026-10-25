"""SCM lifecycle contract tests: simulated Start/Stop, NO SCM registration.

Windows-only once optional pywin32 is installed in a disposable runner.
The service class is exercised without running the Service Control Manager.
"""
from pathlib import Path
import os
import threading
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.name == "nt", "SCM Windows API only")
class QuotaScmLifecycleTests(unittest.TestCase):
    def setUp(self):
        from facekids import quota_broker_scm_win as service_mod
        if service_mod._ServiceBase is object:
            self.skipTest("pywin32 dependency not installed")
        self.mod = service_mod

    def make_fake_instance(self):
        # Directly instantiate the class WITHOUT registering service
        # controls or calling ServiceFramework.__init__.
        instance = object.__new__(self.mod.FaceKidsQuotaLabService)
        instance._stop_signal = threading.Event()
        instance._supervisor = None
        status = []
        instance.ReportServiceStatus = lambda value: status.append(value)
        return instance, status

    def test_start_uses_only_protected_configuration_and_stop_signal(self):
        instance, status = self.make_fake_instance()
        fake_config = (
            r"\\.\pipe\FaceKidsQuotaBrokerLab-" + "a" * 32,
            Path("synthetic-lab.sqlite3"),
            {"S-1-5-21-1-2-3-1001": 1},
        )
        observed = {}

        class StubSupervisor:
            def __init__(self, **kwargs):
                observed.update(kwargs)
                self.stop_requested = False

            def run(self):
                observed["ran"] = True

            def request_stop(self):
                self.stop_requested = True

        with patch.object(self.mod, "read_hklm_lab_configuration",
                          return_value=fake_config) as policy, patch.object(
            self.mod, "QuotaLabSupervisor", StubSupervisor
        ):
            instance.SvcDoRun()
            policy.assert_called_once_with()
            self.assertTrue(observed["ran"])
            self.assertIs(observed["stop_event"], instance._stop_signal)
            self.assertEqual(
                observed["enrolled_child_by_sid"],
                {"S-1-5-21-1-2-3-1001": 1},
            )
            self.assertIn(self.mod.win32service.SERVICE_RUNNING, status)
            instance.SvcStop()
            self.assertTrue(instance._stop_signal.is_set())
            self.assertTrue(instance._supervisor.stop_requested)
            self.assertEqual(status[-1], self.mod.win32service.SERVICE_STOP_PENDING)

    def test_stop_before_supervisor_is_ready_is_safe(self):
        instance, status = self.make_fake_instance()
        instance.SvcStop()
        self.assertTrue(instance._stop_signal.is_set())
        self.assertEqual(status, [self.mod.win32service.SERVICE_STOP_PENDING])

    def test_missing_registry_policy_never_reports_running(self):
        instance, status = self.make_fake_instance()
        with patch.object(self.mod, "read_hklm_lab_configuration",
                          side_effect=PermissionError("synthetic")), patch.object(
            self.mod.servicemanager, "LogErrorMsg"
        ) as logger:
            with self.assertRaises(PermissionError):
                instance.SvcDoRun()
            logger.assert_called_once()
        self.assertNotIn(self.mod.win32service.SERVICE_RUNNING, status)


if __name__ == "__main__":
    unittest.main()
