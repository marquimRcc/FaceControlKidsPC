import unittest

from facekids.unlock_policy import (
    FacialEvidence, OneUseTicketRegistry, UnlockReason, evaluate_unlock,
)


class UnlockPolicyTest(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.balances = {1: 7200.0, 2: 0.0, 3: 150.0}
        self.face = FacialEvidence(1, 1, 3, True, 99.2)

    def evaluate(self, face=None, balances=None, now=None):
        return evaluate_unlock(
            face if face is not None else self.face,
            self.balances if balances is None else balances,
            self.now if now is None else now,
        )

    def test_authorized_child_while_sibling_exhausted(self):
        self.assertTrue(self.evaluate().permitted)
        exhausted = FacialEvidence(2, 1, 3, True, 99.2)
        self.assertEqual(self.evaluate(exhausted).reason, UnlockReason.NO_QUOTA)
        other = FacialEvidence(3, 1, 3, True, 99.2)
        self.assertTrue(self.evaluate(other).permitted)

    def test_multiple_or_no_faces_never_unlock(self):
        for count in (0, 2, 3):
            face = FacialEvidence(1, count, 3, True, 99)
            self.assertEqual(self.evaluate(face).reason, UnlockReason.NO_SINGLE_FACE)

    def test_unknown_face_is_denied(self):
        self.assertEqual(
            self.evaluate(FacialEvidence(None, 1, 3, True, 99)).reason,
            UnlockReason.UNKNOWN_FACE,
        )

    def test_anti_spoof_must_pass(self):
        self.assertEqual(
            self.evaluate(FacialEvidence(1, 1, 3, False, 99)).reason,
            UnlockReason.NOT_LIVE,
        )

    def test_confirmation_and_recent_capture_are_required(self):
        self.assertEqual(
            self.evaluate(FacialEvidence(1, 1, 2, True, 99)).reason,
            UnlockReason.NOT_CONFIRMED,
        )
        for t in (90.0, 101.0, float("nan")):
            self.assertEqual(
                self.evaluate(FacialEvidence(1, 1, 3, True, t)).reason,
                UnlockReason.STALE_OBSERVATION,
            )

    def test_camera_error_has_precedence(self):
        f = FacialEvidence(1, 1, 3, True, 99, camera_ok=False)
        self.assertEqual(self.evaluate(f).reason, UnlockReason.CAMERA_ERROR)

    def test_invalid_quota_fails_closed(self):
        for x in ("7200", float("nan"), float("inf"), True):
            self.assertEqual(self.evaluate(balances={1: x}).reason, UnlockReason.INVALID_QUOTA)
        self.assertEqual(self.evaluate(balances={}).reason, UnlockReason.NO_QUOTA)

    def test_session_bound_one_use_ticket(self):
        current = [100.0]
        registry = OneUseTicketRegistry(clock=lambda: current[0])
        grant = registry.issue(self.face, self.balances, session_id=5)
        self.assertTrue(grant.verdict.permitted)
        self.assertTrue(grant.ticket)
        self.assertEqual(registry.consume(grant.ticket, 5, self.balances), 1)
        self.assertIsNone(registry.consume(grant.ticket, 5, self.balances))

    def test_session_mismatch_revokes_ticket(self):
        registry = OneUseTicketRegistry(clock=lambda: 100.0)
        ticket = registry.issue(self.face, self.balances, 5).ticket
        self.assertIsNone(registry.consume(ticket, 6, self.balances))
        self.assertIsNone(registry.consume(ticket, 5, self.balances))

    def test_ticket_expiry_and_revocation(self):
        t = [100.0]
        r = OneUseTicketRegistry(clock=lambda: t[0], ttl_seconds=5)
        token = r.issue(self.face, self.balances, 5).ticket
        t[0] = 106
        self.assertIsNone(r.consume(token, 5, self.balances))
        t[0] = 100
        token = r.issue(self.face, self.balances, 5).ticket
        r.revoke_all()
        self.assertIsNone(r.consume(token, 5, self.balances))

    def test_recheck_quota_on_ticket_redemption(self):
        reg = OneUseTicketRegistry(clock=lambda: 100.0)
        token = reg.issue(self.face, self.balances, 5).ticket
        self.assertIsNone(reg.consume(token, 5, {1: 0}))
        self.assertIsNone(reg.consume(token, 5, self.balances))

    def test_only_valid_evidence_issues_token(self):
        r = OneUseTicketRegistry(clock=lambda: 100.0)
        refused = r.issue(FacialEvidence(2, 1, 3, True, 99), self.balances, 5)
        self.assertEqual(refused.verdict.reason, UnlockReason.NO_QUOTA)
        self.assertIsNone(refused.ticket)

    def test_invalid_sessions_fail_before_issue_and_consume(self):
        r = OneUseTicketRegistry(clock=lambda: 100.0)
        for invalid in (-1, True, "5"):
            with self.assertRaises(ValueError):
                r.issue(self.face, self.balances, invalid)
            with self.assertRaises(ValueError):
                r.consume("unused", invalid, self.balances)


if __name__ == "__main__":
    unittest.main()
