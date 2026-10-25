"""Current facial lease -> quota snapshot: three children, one Windows SID."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from facekids.quota_broker_bound_protocol import (
    BOUND_ACTION, BOUND_PROTOCOL, BoundBalance, handle_bound_read,
    validate_bound_reply,
)
from facekids.quota_broker_runtime import ServiceOwnedQuotaRuntime
from facekids.quota_broker_scm_host import ServiceOwnedScmHost
from facekids.quota_broker_wts import WtsSnapshot
from facekids.storage import Storage


class BoundBalanceProtocolTests(unittest.TestCase):
    sid = "S-1-5-21-10-20-30-1001"
    request = b'{"version":"FACEKIDS_BOUND_QUOTA_V1","action":"GET_BOUND_BALANCE"}'

    def test_contract_returns_service_selected_identity_only(self):
        calls = []
        def resolve(sid):
            calls.append(sid)
            return BoundBalance(3, 125, True)
        reply = handle_bound_read(self.request, verified_client_sid=self.sid,
                                  read_bound=resolve)
        self.assertEqual(reply, {
            "status": "OK", "version": BOUND_PROTOCOL,
            "child_id": 3, "remaining_seconds": 125.0,
            "allowed_now": True,
        })
        self.assertEqual(calls, [self.sid])
        self.assertEqual(validate_bound_reply(reply), BoundBalance(3, 125, True))

    def test_child_cannot_choose_profile_time_session_or_mutation(self):
        from json import dumps
        called = []
        for request in (
            {"version": BOUND_PROTOCOL, "action": BOUND_ACTION, "child_id": 3},
            {"version": BOUND_PROTOCOL, "action": BOUND_ACTION, "seconds": 3},
            {"version": BOUND_PROTOCOL, "action": BOUND_ACTION, "session_id": 8},
            {"version": BOUND_PROTOCOL, "action": BOUND_ACTION, "day": "2026-10-25"},
            {"version": BOUND_PROTOCOL, "action": "CHARGE"},
            {"version": BOUND_PROTOCOL, "action": "SET_CHILD"},
            {"version": BOUND_PROTOCOL, "action": "UNLOCK"},
            {"version": "FACEKIDS_QUOTA_V1", "action": "GET_BOUND_BALANCE"},
        ):
            with self.subTest(payload=request):
                reply = handle_bound_read(
                    dumps(request).encode(), verified_client_sid=self.sid,
                    read_bound=lambda sid: called.append(sid),
                )
                self.assertEqual(reply, {"status": "DENY"})
        self.assertEqual(called, [])
        for raw in (
            b'{"version":"FACEKIDS_BOUND_QUOTA_V1","action":"GET_BOUND_BALANCE","action":"CHARGE"}',
            b'{"version":"FACEKIDS_BOUND_QUOTA_V1","action":"GET_BOUND_BALANCE"}' * 8,
            b'[]', b'', b'{"version":null,"action":null}',
        ):
            self.assertEqual(handle_bound_read(
                raw, verified_client_sid=self.sid,
                read_bound=lambda _: BoundBalance(1, 8, True),
            ), {"status": "DENY"})

    def test_invalid_balance_or_identity_fails_closed(self):
        for case in (
            {"status": "OK", "version": BOUND_PROTOCOL, "child_id": True,
             "remaining_seconds": 120, "allowed_now": True},
            {"status": "OK", "version": BOUND_PROTOCOL, "child_id": 2,
             "remaining_seconds": float("nan"), "allowed_now": True},
            {"status": "OK", "version": BOUND_PROTOCOL, "child_id": 2,
             "remaining_seconds": -1, "allowed_now": False},
            {"status": "OK", "version": BOUND_PROTOCOL, "child_id": 2,
             "remaining_seconds": 0, "allowed_now": True},
            {"status": "OK", "version": BOUND_PROTOCOL, "child_id": 2,
             "remaining_seconds": 120, "allowed_now": True, "charge": 99},
        ):
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_bound_reply(case)
        calls = []
        for invalid_sid in ("S-1-bad", "S-1-", "S-1-5", "S-1-5-21-xyz-1", "S-1-5-21\\n", "", None):
            with self.subTest(invalid_sid=invalid_sid):
                self.assertEqual(handle_bound_read(
                    self.request, verified_client_sid=invalid_sid,
                    read_bound=lambda sid: calls.append(sid),
                ), {"status": "DENY"})
        self.assertEqual(calls, [], "Malformed token SID must never reach quota reader")
        self.assertEqual(handle_bound_read(
            self.request, verified_client_sid="forged-user",
            read_bound=lambda _: BoundBalance(1, 200, True)
        ), {"status": "DENY"})
        self.assertEqual(handle_bound_read(
            self.request, verified_client_sid=self.sid,
            read_bound=lambda _: None,
        ), {"status": "DENY"})


class FaceBoundHostTests(unittest.TestCase):
    sid = "S-1-5-21-1-2-3-1001"

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.store = Storage(Path(self.temp.name) / "three-kids.sqlite3")
        self.children = tuple(
            self.store.add_person(f"Child {n}", 2)
            for n in range(1, 4)
        )
        self.now = 100.0
        self.wts = WtsSnapshot(23, self.sid, True)
        self.face = self.children[0]
        self.auth_enabled = True
        self.runtime = ServiceOwnedQuotaRuntime(
            self.store, expected_windows_sid=self.sid,
            observe_wts=lambda: self.wts,
            capture_face_locally=lambda: (
                ("ALLOW", {"user": "Filhos", "child_id": self.face})
                if self.auth_enabled else ("DENY", {})
            ),
            monotonic=lambda: self.now, today=lambda: date(2026, 10, 25),
        )
        self.host = ServiceOwnedScmHost(
            self.runtime, monotonic=lambda: self.now
        )

    def tearDown(self):
        self.host.request_stop()
        self.store.close()
        self.temp.cleanup()

    def lookup(self, sid=None):
        return self.host.read_bound_balance(
            verified_client_sid=sid or self.sid
        )

    def test_three_children_same_token_fresh_lease_and_independent_quotas(self):
        self.assertIsNone(self.lookup())
        for index, child in enumerate(self.children):
            self.face = child
            self.host.on_scm_session_change(8, (23,))
            self.assertIsNone(self.lookup(), "Unlock alone cannot select a child")
            first = self.host.step()
            self.assertEqual(first.child_id, child)
            bound = self.lookup()
            self.assertEqual(bound, BoundBalance(child, 120, True))
            self.assertIsNone(self.lookup("S-1-5-18"))
            self.now += 3 + index
            paid = self.host.step()
            self.assertEqual(paid.charged_seconds, 3 + index)
            self.assertEqual(self.lookup().remaining_seconds, 120 - 3 - index)
            self.host.on_scm_session_change(7, (23,))
            self.assertIsNone(self.lookup(), "Win+L must revoke old face identity")
            self.now += 2
            self.assertIsNone(self.lookup())
        self.assertEqual(
            [self.store.used(child, "2026-10-25") for child in self.children],
            [3, 4, 5],
        )

    def test_disconnected_wrong_sid_failed_face_and_stop_are_denied(self):
        self.host.on_scm_session_change(8, (23,))
        self.host.step()
        self.assertIsNotNone(self.lookup())
        self.wts = WtsSnapshot(23, "S-1-5-18", True)
        self.assertIsNone(self.lookup())
        self.wts = WtsSnapshot(23, self.sid, False)
        self.assertIsNone(self.lookup())
        self.wts = WtsSnapshot(23, self.sid, True)
        self.host.on_scm_session_change(7, (23,))
        self.host.on_scm_session_change(8, (23,))
        self.auth_enabled = False
        self.host.step()
        self.assertIsNone(self.lookup())
        self.host.request_stop()
        self.assertIsNone(self.lookup())

    def test_stale_read_does_not_prolong_face_authorization(self):
        self.host.on_scm_session_change(8, (23,))
        self.host.step()
        self.now += 7
        self.assertIsNone(self.lookup())
        self.assertEqual(self.store.used(self.face, "2026-10-25"), 0)
        self.host.step()
        self.assertIsNotNone(self.lookup())

    def test_concurrent_lock_during_capture_can_never_publish_old_child(self):
        begin = threading.Event()
        release = threading.Event()
        outcomes = []
        def capture():
            begin.set()
            if not release.wait(3):
                raise TimeoutError("synthetic camera")
            return "ALLOW", {"user": "Filhos", "child_id": self.children[0]}
        runtime = ServiceOwnedQuotaRuntime(
            self.store, expected_windows_sid=self.sid,
            observe_wts=lambda: self.wts, capture_face_locally=capture,
            monotonic=lambda: self.now, today=lambda: date(2026, 10, 25),
        )
        host = ServiceOwnedScmHost(runtime, monotonic=lambda: self.now)
        host.on_scm_session_change(8, (23,))
        worker = threading.Thread(target=lambda: outcomes.append(host.step()), daemon=True)
        try:
            worker.start()
            self.assertTrue(begin.wait(2))
            self.assertIsNone(host.read_bound_balance(verified_client_sid=self.sid))
            host.on_scm_session_change(7, (23,))
            release.set()
            worker.join(4)
            self.assertFalse(worker.is_alive())
            self.assertIsNone(host.read_bound_balance(verified_client_sid=self.sid))
            self.assertEqual(outcomes[0].charged_seconds, 0)
        finally:
            release.set()
            host.request_stop()


if __name__ == "__main__":
    unittest.main()
