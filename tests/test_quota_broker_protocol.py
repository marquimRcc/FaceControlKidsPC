"""Synthetic read-only broker protocol tests. No Windows service or pipe."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from facekids.quota_broker_protocol import (
    BROKER_PROTOCOL, MAX_REQUEST_BYTES, VerifiedClient, handle_broker_read,
)
from facekids.storage import Storage


class BrokerReadProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "broker.sqlite3")
        self.child = self.store.add_person("First", 60)
        self.other = self.store.add_person("Second", 120)
        self.sid = "S-1-5-21-1111-2222-3333-1001"
        self.identity = VerifiedClient(self.sid, self.sid, self.child)
        self.today = date(2026, 10, 24)
        self.request = b'{"version":"FACEKIDS_QUOTA_V1","action":"GET_BALANCE"}'

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def call(self, payload=None, identity=None):
        return handle_broker_read(
            self.request if payload is None else payload,
            self.identity if identity is None else identity,
            self.store, observed_day=self.today,
        )

    def test_authenticated_balance_only_reads_own_enrollment(self):
        self.store.charge(self.child, 100, self.today.isoformat())
        self.assertEqual(self.call()["remaining_seconds"], 3500)
        self.assertTrue(self.call()["allowed_now"])
        self.assertEqual(self.store.used(self.child, self.today.isoformat()), 100)
        self.assertEqual(self.store.used(self.other, self.today.isoformat()), 0)

    def test_ping_requires_authenticated_identity(self):
        req = b'{"version":"FACEKIDS_QUOTA_V1","action":"PING"}'
        self.assertEqual(self.call(req), {"status": "OK", "version": BROKER_PROTOCOL})
        self.assertEqual(
            self.call(req, VerifiedClient("S-1-5-18", self.sid, self.child)),
            {"status": "DENY"},
        )

    def test_client_cannot_select_child_date_or_debit(self):
        for addition in ('"child_id":2', '"day":"2026-10-25"', '"seconds":-900',
                         '"action":"GET_BALANCE"', '"is_admin":true'):
            request = ('{"version":"FACEKIDS_QUOTA_V1","action":"GET_BALANCE",'
                       + addition + '}').encode()
            with self.subTest(addition=addition):
                self.assertEqual(self.call(request), {"status": "DENY"})
        for action in ("CHARGE", "RESET_QUOTA", "ADD_BONUS", "SET_IDENTITY"):
            payload = ('{"version":"FACEKIDS_QUOTA_V1","action":"'
                       + action + '"}').encode()
            with self.subTest(action=action):
                self.assertEqual(self.call(payload), {"status": "DENY"})
        self.assertEqual(self.store.used(self.child, self.today.isoformat()), 0)

    def test_malformed_replayed_and_oversized_payloads_rejected(self):
        for payload in (b'{}', b'[]', b'null', b'{"action":"PING"}',
                        b'{"version":"FACEKIDS_QUOTA_V1","action":"PING","action":"GET_BALANCE"}',
                        b'{"version":"FACEKIDS_QUOTA_V1","action":"PING"}\x00',
                        b'{"version":"FACEKIDS_QUOTA_V1","action":"PING"}junk',
                        b'{"version":"FACEKIDS_QUOTA_V1","action":"PING","n":NaN}',
                        b'X' * (MAX_REQUEST_BYTES + 1), b'', b'\xff'):
            with self.subTest(payload=payload[:55]):
                self.assertEqual(self.call(payload), {"status": "DENY"})

    def test_never_trust_empty_or_wrong_token_sid(self):
        for obj in (
            VerifiedClient("", "", self.child),
            VerifiedClient(self.sid, "S-1-5-18", self.child),
            VerifiedClient(self.sid, self.sid, True),
            VerifiedClient(self.sid, self.sid, 0),
            VerifiedClient("Filhos", "Filhos", self.child),
        ):
            self.assertEqual(self.call(identity=obj), {"status": "DENY"})

    def test_curfew_and_exhaustion_return_no_permission(self):
        self.store.charge(self.child, 3600, self.today.isoformat())
        exhausted = self.call()
        self.assertEqual(exhausted["remaining_seconds"], 0)
        self.assertFalse(exhausted["allowed_now"])
        self.store.add_bonus(self.child, 1, self.today.isoformat())
        from unittest.mock import patch
        with patch.object(self.store, "is_curfew_active", return_value=(True, "blocked")):
            self.assertFalse(self.call()["allowed_now"])


if __name__ == "__main__":
    unittest.main()
