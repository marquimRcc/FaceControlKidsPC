"""Quota source boundary: a lab status packet can NEVER debit or lock Windows."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import inspect
import unittest
from unittest.mock import MagicMock, patch

from facekids.quota_agent_accounting import (
    BrokerLabReadOnlyQuota, LegacyLedgerQuota, QuotaTick,
    UntrustedBrokerObservation,
)
from facekids.quota_broker_protocol import BROKER_PROTOCOL, VerifiedClient, handle_broker_read
from facekids.quota_broker_read_store import ReadOnlyQuotaView
from facekids.storage import Storage


class QuotaAgentSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="facekids-agent-readonly-")
        self.path = Path(self.tmp.name) / "synthetic.sqlite3"
        self.store = Storage(self.path)
        self.people = [self.store.add_person("Synthetic " + str(i), 2)
                       for i in (1, 2, 3)]
        self.day = "2026-10-25"

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def valid_response(self, balance=120, allowed=True):
        return {
            "status": "OK", "version": BROKER_PROTOCOL,
            "remaining_seconds": balance, "allowed_now": allowed,
        }

    def test_legacy_live_loop_debits_exactly_once(self):
        adapter = LegacyLedgerQuota(self.store)
        status = adapter.active_tick(child_id=self.people[0], seconds=3, day=self.day)
        self.assertEqual(status, QuotaTick(117.0, True, True))
        self.assertEqual(self.store.used(self.people[0], self.day), 3)
        self.assertEqual(self.store.used(self.people[1], self.day), 0)

    def test_legacy_invalid_delta_never_mutates(self):
        adapter = LegacyLedgerQuota(self.store)
        for delta in (float("nan"), float("inf"), True, -1, 0, 15.1):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                adapter.active_tick(child_id=self.people[0], seconds=delta, day=self.day)
        self.assertEqual(self.store.used(self.people[0], self.day), 0)

    def test_untrusted_broker_can_observe_but_never_charge_or_lock(self):
        query = MagicMock(return_value=self.valid_response(120, True))
        source = BrokerLabReadOnlyQuota(query)
        observation = source.observe()
        self.assertEqual(observation, UntrustedBrokerObservation("observed", 120.0, True))
        self.assertFalse(observation.charged_locally)
        self.assertFalse(observation.may_enforce_lock)
        self.assertFalse(hasattr(source, "active_tick"))
        self.assertFalse(hasattr(source, "charge"))
        self.assertFalse(hasattr(source, "store"))
        self.assertFalse(hasattr(source, "switch_child"))
        self.assertEqual(self.store.used(self.people[0], self.day), 0)

    def test_forged_broker_reply_may_not_force_unlock_or_lock(self):
        for response in (
            self.valid_response(0, True),
            self.valid_response(float("nan")),
            self.valid_response(float("inf")),
            self.valid_response(-1),
            self.valid_response(False),
            {"status": "OK", "version": "fake", "remaining_seconds": 1, "allowed_now": True},
            {**self.valid_response(), "child_id": self.people[1]},
            {**self.valid_response(), "elapsed_seconds": 999999},
            {"status": "DENY"},
        ):
            with self.subTest(reply=response):
                obs = BrokerLabReadOnlyQuota(lambda response=response: response).observe()
                self.assertFalse(obs.may_enforce_lock)
                self.assertFalse(obs.charged_locally)
                self.assertEqual(self.store.used(self.people[0], self.day), 0)

    def test_timeout_and_transient_failures_are_read_only(self):
        for exc in (TimeoutError("test"), OSError("down"), ValueError("bad")):
            obs = BrokerLabReadOnlyQuota(lambda exc=exc: (_ for _ in ()).throw(exc)).observe()
            self.assertEqual(obs.status, "unavailable")
            self.assertIsNone(obs.remaining_seconds)
            self.assertFalse(obs.may_enforce_lock)

    def test_service_protocol_and_readonly_sqlite_keep_child_identity_server_side(self):
        self.store.charge(self.people[0], 10, self.day)
        self.store.charge(self.people[1], 20, self.day)
        self.store.charge(self.people[2], 30, self.day)
        self.store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        with ReadOnlyQuotaView(self.path) as reader:
            source = BrokerLabReadOnlyQuota(lambda: handle_broker_read(
                b'{"version":"FACEKIDS_QUOTA_V1","action":"GET_BALANCE"}',
                VerifiedClient("S-1-5-21-1-2-3-1001", "S-1-5-21-1-2-3-1001",
                               self.people[1]),
                reader, observed_day=date(2026, 10, 25),
            ))
            obs = source.observe()
        self.assertEqual(obs.remaining_seconds, 100)
        self.assertFalse(obs.may_enforce_lock)
        self.assertEqual([self.store.used(i, self.day) for i in self.people], [10, 20, 30])

    def test_actual_agent_preserves_legacy_mode_until_security_cutover(self):
        from facekids import filhos_agent
        source = inspect.getsource(filhos_agent.run_agent)
        self.assertIn("LegacyLedgerQuota(store)", source)
        self.assertIn("quota_accounting.active_tick", source)
        self.assertNotIn("store.charge(", source)
        self.assertIn("if tick.may_enforce_lock else False", source)
        self.assertNotIn("BrokerLabReadOnlyQuota(", source)


if __name__ == "__main__":
    unittest.main()
