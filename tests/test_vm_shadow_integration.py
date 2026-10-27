"""P5 non-authoritative VM telemetry: session/identity/fail-soft regression."""
import inspect
import unittest
from unittest.mock import Mock

from facekids.quota_broker_bound_protocol import BoundBalance
from facekids.quota_vm_shadow_integration import (
    VmBoundShadow, shadow_enabled_for_vm,
)
from facekids import filhos_agent


class Clock:
    def __init__(self):
        self.now = 100.0
    def __call__(self):
        return self.now


class ShadowVmIntegrationTests(unittest.TestCase):
    def make(self, value=None, raises=False):
        clock = Clock()
        def query():
            if raises:
                raise TimeoutError("VM service unavailable")
            return value
        return VmBoundShadow(query=query, clock=clock, interval_seconds=15), clock

    def poll(self, probe, *, child=4, day="2026-10-27", balance=100):
        probe.trigger_if_due(child_id=child, day=day, remaining_seconds=balance)
        probe._thread.join(timeout=2)
        return probe.take_result(
            current_child_id=child, current_day=day,
            current_remaining=balance)

    def test_default_off_even_in_windows_and_unrecognized_optin(self):
        self.assertFalse(shadow_enabled_for_vm({}, windows=True))
        self.assertFalse(shadow_enabled_for_vm(
            {"FACEKIDS_VM_SHADOW": "1"}, windows=True))
        self.assertFalse(shadow_enabled_for_vm({
            "FACEKIDS_VM_SHADOW": "1",
            "FACEKIDS_VM_SHADOW_ACK": "DISPOSABLE_VM_ONLY"}, windows=False))
        self.assertTrue(shadow_enabled_for_vm({
            "FACEKIDS_VM_SHADOW": "1",
            "FACEKIDS_VM_SHADOW_ACK": "DISPOSABLE_VM_ONLY"}, windows=True))

    def test_same_child_same_context_compared_only_telemetrically(self):
        p, _ = self.make(BoundBalance(4, 100.5, True))
        r = self.poll(p)
        self.assertEqual(r.outcome, "matched")
        self.assertAlmostEqual(r.difference_seconds, 0.5)
        self.assertIsNone(p.take_result(
            current_child_id=4, current_day="2026-10-27",
            current_remaining=100))

    def test_another_child_is_never_compared_as_current_player(self):
        p, _ = self.make(BoundBalance(3, 9000, True))
        r = self.poll(p)
        self.assertEqual(r.outcome, "different-face-lease")
        self.assertIsNone(r.difference_seconds)

    def test_stale_identity_local_clock_and_day_do_not_compare(self):
        for change in (
            {"current_child_id": 9, "current_day": "2026-10-27",
             "current_remaining": 100},
            {"current_child_id": 4, "current_day": "2026-10-28",
             "current_remaining": 100},
            {"current_child_id": 4, "current_day": "2026-10-27",
             "current_remaining": 96},
        ):
            with self.subTest(change=change):
                p, _ = self.make(BoundBalance(4, 100, True))
                p.trigger_if_due(child_id=4, day="2026-10-27", remaining_seconds=100)
                p._thread.join(timeout=2)
                r = p.take_result(**change)
                self.assertIn(r.outcome, ("local-context-changed", "incomparable-sample"))
                self.assertIsNone(r.difference_seconds)

    def test_nonblocking_failures_unbound_and_rate_limit(self):
        for val, error, expected in (
            (None, False, "unbound"),
            (None, True, "unavailable"),
        ):
            p, clock = self.make(val, raises=error)
            self.assertEqual(self.poll(p).outcome, expected)
            p.trigger_if_due(child_id=4, day="2026-10-27", remaining_seconds=100)
            self.assertIsNone(p.take_result(
                current_child_id=4, current_day="2026-10-27", current_remaining=100))
            clock.now += 15
            self.assertEqual(self.poll(p).outcome, expected)

    def test_readonly_shadow_never_controls_agent_authority(self):
        source = inspect.getsource(filhos_agent.run_agent)
        self.assertIn("shadow_enabled_for_vm()", source)
        self.assertIn("shadow_probe.trigger_if_due(", source)
        self.assertIn("shadow_probe.take_result(", source)
        self.assertIn("LegacyLedgerQuota(store)", source)
        self.assertIn("tracker.check_notifications_and_lock(rem)", source)
        self.assertNotIn("BrokerLabReadOnlyQuota(store)", source)


if __name__ == "__main__":
    unittest.main()
