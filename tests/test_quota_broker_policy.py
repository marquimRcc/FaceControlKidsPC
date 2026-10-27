"""Synthetic service-owned quota broker tests; no login/Windows service."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from facekids.quota_broker_policy import ServiceOwnedQuotaBroker
from facekids.storage import Storage


class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


class ServiceOwnedQuotaBrokerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "ledger.sqlite3")
        self.first = self.storage.add_person("First", 1)
        self.second = self.storage.add_person("Second", 2)
        self.clock = Clock()
        self.broker = ServiceOwnedQuotaBroker(
            self.storage, monotonic=self.clock, today=lambda: date(2026, 10, 24)
        )
        self.day = "2026-10-24"

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def activate(self, child=None, session=42):
        return self.broker.start_verified_session(
            child_id=self.first if child is None else child,
            session_id=session,
            console_active=True,
        )

    def tick(self, now, session=42, active=True):
        self.clock.now = now
        return self.broker.observe(
            observed_wts_session_id=session,
            observed_console_active=active,
        )

    def test_service_generated_receipts_persist_and_prevent_reuse(self):
        from unittest.mock import patch
        receipt = "0" * 32
        broker = ServiceOwnedQuotaBroker(
            self.storage,
            monotonic=self.clock,
            today=lambda: date(2026, 10, 24),
            new_receipt_id=lambda: receipt,
        )
        self.assertEqual(
            broker.start_verified_session(
                child_id=self.first, session_id=42, console_active=True
            ).reason, "verified"
        )
        self.clock.now = 103
        self.assertEqual(broker.observe(
            observed_wts_session_id=42, observed_console_active=True
        ).charged_seconds, 3.0)
        self.assertEqual(self.storage.used(self.first, self.day), 3.0)
        row = self.storage.db.execute(
            "SELECT charged_seconds FROM quota_tick_receipts WHERE event_id=?",
            (receipt,)
        ).fetchone()
        self.assertEqual(row, (3.0,))
        # Identical replay is idempotent and charges zero. Reuse with a
        # DIFFERENT interval must fail closed instead of double-charging.
        self.clock.now = 106
        self.assertEqual(broker.observe(
            observed_wts_session_id=42, observed_console_active=True
        ).charged_seconds, 0.0)
        self.assertEqual(self.storage.used(self.first, self.day), 3.0)
        self.clock.now = 110
        with self.assertRaises(ValueError):
            broker.observe(
                observed_wts_session_id=42, observed_console_active=True
            )
        self.assertEqual(self.storage.used(self.first, self.day), 3.0)

    def test_charge_only_service_elapsed_time_and_child(self):
        self.assertEqual(self.activate().reason, "verified")
        self.assertEqual(self.tick(104).charged_seconds, 4)
        self.assertEqual(self.storage.used(self.first, self.day), 4)
        self.assertEqual(self.storage.used(self.second, self.day), 0)
        self.assertEqual(self.tick(106).remaining_seconds, 54)

    def test_win_lock_revokes_lease_and_requires_new_face_verification(self):
        self.activate()
        self.assertEqual(self.tick(103, active=False).charged_seconds, 0)
        self.assertEqual(self.tick(106, active=True).reason, "no-verified-lease")
        self.assertEqual(self.storage.used(self.first, self.day), 0)
        self.clock.now = 106
        self.activate()  # independent trusted WTS + facial re-verification
        self.assertEqual(self.tick(109).charged_seconds, 3)
        self.assertEqual(self.tick(50_000, active=False).charged_seconds, 0)
        self.assertEqual(self.tick(50_003, active=True).reason, "no-verified-lease")
        self.assertEqual(self.storage.used(self.first, self.day), 3)

    def test_session_switch_revokes_previous_lease(self):
        self.activate()
        switched = self.tick(103, session=99)
        self.assertEqual(switched.reason, "session-switched")
        self.assertEqual(switched.charged_seconds, 0)
        self.assertEqual(self.tick(105).reason, "no-verified-lease")
        self.assertEqual(self.storage.used(self.first, self.day), 0)

    def test_child_switch_resets_lease_without_cross_charging(self):
        self.activate()
        self.tick(105)
        self.clock.now = 108
        self.activate(self.second)
        self.assertEqual(self.tick(110).charged_seconds, 2)
        self.assertEqual(self.storage.used(self.first, self.day), 5)
        self.assertEqual(self.storage.used(self.second, self.day), 2)

    def test_exhaustion_caps_debit_and_requires_new_verification(self):
        self.activate()
        self.assertEqual(self.tick(115).charged_seconds, 15)
        self.assertEqual(self.tick(130).charged_seconds, 15)
        self.assertEqual(self.tick(145).charged_seconds, 15)
        final = self.tick(160)
        self.assertTrue(final.locked)
        self.assertEqual(final.charged_seconds, 15)
        self.assertEqual(final.remaining_seconds, 0)
        self.assertEqual(self.tick(170).reason, "no-verified-lease")
        self.assertEqual(self.activate().reason, "quota")
        self.assertEqual(self.storage.used(self.first, self.day), 60)

    def test_curfew_does_not_charge_and_revokes_lease(self):
        self.activate()
        self.storage.set_curfew_config(True, "00:00", "00:00")
        # Avoid using the host's current clock to decide a real curfew;
        # patch the storage observation instead.
        from unittest.mock import patch
        with patch.object(self.storage, "is_curfew_active", return_value=(True, "test")):
            result = self.tick(104)
        self.assertTrue(result.locked)
        self.assertEqual(result.reason, "curfew")
        self.assertEqual(self.storage.used(self.first, self.day), 0)

    def test_broker_never_grants_unknown_or_unverified_lease(self):
        self.assertEqual(self.broker.observe(
            observed_wts_session_id=42, observed_console_active=True
        ).reason, "no-verified-lease")
        self.assertEqual(self.activate(child=9_999).reason, "unknown-child")
        result = self.broker.start_verified_session(
            child_id=self.first, session_id=42, console_active=False
        )
        self.assertEqual(result.reason, "not-active")
        with self.assertRaises(ValueError):
            self.activate(child=True)
        with self.assertRaises(ValueError):
            self.activate(session=0)
        self.assertEqual(self.storage.used(self.first, self.day), 0)

    def test_suspend_and_clock_anomalies_not_billed(self):
        self.activate()
        self.assertEqual(self.tick(50_000).charged_seconds, 0)
        self.assertEqual(self.tick(50_001).charged_seconds, 1)
        self.assertEqual(self.tick(40_000).charged_seconds, 0)
        self.assertEqual(self.tick(40_002).charged_seconds, 2)

    def test_reject_nonfinite_clock_and_fake_session_flags(self):
        self.activate()
        for now in (float("nan"), float("inf"), -1, True):
            self.clock.now = now
            with self.subTest(now=now), self.assertRaises(ValueError):
                self.broker.observe(
                    observed_wts_session_id=42, observed_console_active=True
                )
        self.clock.now = 102
        with self.assertRaises(ValueError):
            self.broker.observe(observed_wts_session_id=True,
                                observed_console_active=True)
        with self.assertRaises(ValueError):
            self.broker.observe(observed_wts_session_id=42,
                                observed_console_active=1)
        self.assertEqual(self.storage.used(self.first, self.day), 0)


if __name__ == "__main__":
    unittest.main()
