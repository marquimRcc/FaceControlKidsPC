"""Portable lifecycle tests; no service registration or Windows login."""
from pathlib import Path
import threading
import unittest

from facekids.quota_broker_supervisor import QuotaLabSupervisor


class SupervisorTests(unittest.TestCase):
    def make_supervisor(self, worker, **kwargs):
        return QuotaLabSupervisor(
            pipe_name=r"\\.\pipe\FaceKidsQuotaBrokerLab-" + "a" * 32,
            data_path=Path("synthetic"), enrolled_child_by_sid={"S-1-5-18": 1},
            serve_one=worker, **kwargs,
        )

    def test_supervisor_continues_from_synthetic_success_and_stops(self):
        seen = []
        supervisor = None

        def worker(**kwargs):
            seen.append(kwargs)
            if len(seen) == 4:
                supervisor.request_stop()
            return len(seen) % 2 == 0

        supervisor = self.make_supervisor(worker)
        supervisor.run()
        self.assertEqual(supervisor.processed, 2)
        self.assertEqual(supervisor.timeout_cycles, 2)
        self.assertEqual(supervisor.errors, 0)
        self.assertEqual(len(seen), 4)
        self.assertTrue(all(item["stop_event"] is supervisor.stop_event for item in seen))
        self.assertTrue(all(item["timeout_seconds"] == 2.0 for item in seen))

    def test_stop_before_running_does_not_open_pipe(self):
        invoked = []
        supervisor = self.make_supervisor(lambda **kwargs: invoked.append(kwargs))
        supervisor.request_stop()
        supervisor.run()
        self.assertEqual(invoked, [])

    def test_recover_transient_failure_then_resume(self):
        calls = []
        supervisor = None

        def worker(**kwargs):
            calls.append(len(calls))
            if len(calls) == 1:
                raise OSError("synthetic transient error")
            supervisor.request_stop()
            return True

        supervisor = self.make_supervisor(worker, retry_interval_seconds=0.05)
        supervisor.run()
        self.assertEqual(supervisor.errors, 1)
        self.assertEqual(supervisor.processed, 1)
        self.assertEqual(supervisor.last_error, "OSError")

    def test_repeated_failure_stops_service_instead_of_spinning(self):
        calls = []

        def worker(**kwargs):
            calls.append(1)
            raise PermissionError("mock ACL denied")

        supervisor = self.make_supervisor(
            worker, max_consecutive_failures=2, retry_interval_seconds=0.05
        )
        with self.assertRaisesRegex(RuntimeError, "fail-closed"):
            supervisor.run()
        self.assertEqual(len(calls), 2)
        self.assertEqual(supervisor.errors, 2)
        self.assertEqual(supervisor.last_error, "PermissionError")

    def test_invalid_lifecycle_configuration_fails(self):
        for options in (
            {"max_consecutive_failures": 0},
            {"max_consecutive_failures": True},
            {"retry_interval_seconds": 0},
            {"retry_interval_seconds": 100},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.make_supervisor(lambda **kwargs: False, **options)


if __name__ == "__main__":
    unittest.main()
