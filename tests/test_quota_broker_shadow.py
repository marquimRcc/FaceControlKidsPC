"""Shadow diagnostics never modify the active screen-time enforcement."""
import unittest
from unittest.mock import patch

from facekids.quota_broker_shadow import (
    QuotaBrokerShadowProbe, compare_shadow_balance,
)


class BrokerShadowTests(unittest.TestCase):
    def test_comparison_is_purely_diagnostic(self):
        self.assertEqual(compare_shadow_balance(50, {
            "status": "OK", "remaining_seconds": 50.5,
        }), ("matched", 0.5))
        self.assertEqual(compare_shadow_balance(50, {
            "status": "OK", "remaining_seconds": 60,
        }), ("diverged", 10.0))
        self.assertEqual(compare_shadow_balance(50, {"status": "DENY"}),
                         ("broker-unavailable", None))
        self.assertEqual(compare_shadow_balance(50, {
            "status": "OK", "remaining_seconds": float("nan"),
        }), ("broker-invalid", None))
        self.assertEqual(compare_shadow_balance(True, {
            "status": "OK", "remaining_seconds": 10,
        }), ("local-invalid", None))

    def test_background_probe_cannot_apply_screen_time_mutation(self):
        suffix = "0123456789abcdef0123456789abcdef"
        probe = QuotaBrokerShadowProbe(suffix, interval_seconds=120)
        expected = {"status": "OK", "remaining_seconds": 59}
        with patch("facekids.quota_broker_shadow.query_lab_balance",
                   return_value=expected) as query, patch(
            "facekids.quota_broker_shadow.time.monotonic",
            return_value=1000.0,
        ):
            probe.trigger_if_due()
            probe._thread.join(timeout=1)
            self.assertEqual(probe.take_result(), expected)
            self.assertIsNone(probe.take_result())
            probe.trigger_if_due()
            query.assert_called_once_with(probe.pipe_name)

    def test_failed_query_is_non_authoritative(self):
        probe = QuotaBrokerShadowProbe("0" * 32)
        with patch("facekids.quota_broker_shadow.query_lab_balance",
                   side_effect=TimeoutError("synthetic")):
            with patch("facekids.quota_broker_shadow.time.monotonic",
                       return_value=1000):
                probe.trigger_if_due()
                probe._thread.join(timeout=1)
                self.assertEqual(probe.take_result(), {"status": "DENY"})

    def test_reject_bad_lab_suffix(self):
        for suffix in ("", "../", "A" * 32, "a" * 31):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                QuotaBrokerShadowProbe(suffix)


if __name__ == "__main__":
    unittest.main()
