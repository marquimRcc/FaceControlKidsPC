"""Synthetic service-owned quota-clock policy tests (no Windows services)."""
import unittest

from facekids.quota_broker_clock import ServerObservedQuotaClock


class ServerObservedQuotaClockTests(unittest.TestCase):
    def make_clock(self):
        return ServerObservedQuotaClock(child_id=1, session_id=42, last_mono=100.0)

    def tick(self, clock, *, now=102.0, child=1, session=42, active=True):
        return clock.sample(
            observed_child_id=child,
            observed_wts_session_id=session,
            observed_wts_active=active,
            now_mono=now,
        )

    def test_charge_server_observed_elapsed_without_client_seconds(self):
        clock = self.make_clock()
        self.assertEqual(self.tick(clock, now=102.0), 2.0)
        self.assertEqual(self.tick(clock, now=104.5), 2.5)

    def test_locked_or_switched_session_does_not_build_billable_backlog(self):
        clock = self.make_clock()
        self.assertEqual(self.tick(clock, now=102, active=False), 0)
        self.assertEqual(self.tick(clock, now=103, active=True), 1)
        self.assertEqual(self.tick(clock, now=200, active=True), 0)
        self.assertEqual(self.tick(clock, now=202, active=True), 2)

    def test_child_and_wts_session_mismatch_rejected_without_moving_clock(self):
        clock = self.make_clock()
        for child, session in ((2, 42), (1, 43), (True, 42), (1, False)):
            with self.subTest(child=child, session=session), self.assertRaises(ValueError):
                self.tick(clock, now=105, child=child, session=session)
            self.assertEqual(clock.last_mono, 100)
        self.assertEqual(self.tick(clock, now=105), 5)

    def test_invalid_clock_and_wts_state_rejected(self):
        clock = self.make_clock()
        for now in (float("nan"), float("inf"), -1, "105", True):
            with self.subTest(now=now), self.assertRaises(ValueError):
                self.tick(clock, now=now)
        with self.assertRaises(ValueError):
            self.tick(clock, active=1)
        self.assertEqual(clock.last_mono, 100)

    def test_backward_monotonic_timestamp_never_debits(self):
        clock = self.make_clock()
        self.assertEqual(self.tick(clock, now=99), 0)
        self.assertEqual(self.tick(clock, now=100), 1)

    def test_two_children_do_not_share_time_state(self):
        first = self.make_clock()
        second = ServerObservedQuotaClock(child_id=2, session_id=42, last_mono=100)
        self.assertEqual(self.tick(first, now=104), 4)
        self.assertEqual(self.tick(second, now=103, child=2), 3)
        self.assertEqual(first.last_mono, 104)
        self.assertEqual(second.last_mono, 103)

    def test_bad_constructor_values_fail(self):
        for kwargs in (
            dict(child_id=0, session_id=42, last_mono=100),
            dict(child_id=1, session_id=0, last_mono=100),
            dict(child_id=1, session_id=42, last_mono=float("inf")),
            dict(child_id=1, session_id=42, last_mono=100, max_tick_seconds=0),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ServerObservedQuotaClock(**kwargs)


if __name__ == "__main__":
    unittest.main()
