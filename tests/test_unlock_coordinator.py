import unittest

from facekids.unlock_coordinator import (
    BridgeStatus, OfflineUnlockCoordinator, WindowsSession,
)
from facekids.unlock_policy import FacialEvidence, UnlockReason


CHILD = "S-1-5-21-100-200-300-1005"
PARENT = "S-1-5-21-100-200-300-1001"
OTHER = "S-1-5-21-100-200-300-1007"


class UnlockCoordinatorTest(unittest.TestCase):
    def setUp(self):
        self.clock = [100.0]
        self.session = WindowsSession(7, CHILD, True)
        self.balances = {1: 7200.0, 2: 0.0, 3: 600.0}
        self.coordinator = OfflineUnlockCoordinator(
            target_sid=CHILD, parent_sid=PARENT,
            read_session=lambda _: self.session,
            read_remaining=lambda child: self.balances[child],
            clock=lambda: self.clock[0],
        )

    def face(self, child=1, **changes):
        fields = dict(child_id=child, face_count=1, confirmations=3,
                      live=True, observed_at=self.clock[0] - .2)
        fields.update(changes)
        return FacialEvidence(**fields)

    def test_success_one_use_and_independent_sibling_quotas(self):
        self.assertEqual(self.coordinator.record_trusted_face(self.face(), 7).status, BridgeStatus.PENDING)
        result = self.coordinator.consume_for_logonui(7)
        self.assertEqual(result.status, BridgeStatus.GRANTED)
        self.assertEqual(result.child_id, 1)
        self.assertEqual(self.coordinator.consume_for_logonui(7).status, BridgeStatus.NO_AUTHORIZATION)
        exhausted = self.coordinator.record_trusted_face(self.face(2), 7)
        self.assertEqual(exhausted.status, BridgeStatus.EVIDENCE_DENIED)
        self.assertEqual(exhausted.evidence_reason, UnlockReason.NO_QUOTA)
        self.assertEqual(self.coordinator.record_trusted_face(self.face(3), 7).status, BridgeStatus.PENDING)
        self.assertEqual(self.coordinator.consume_for_logonui(7).child_id, 3)

    def test_parent_sid_never_receives_authorization(self):
        self.session = WindowsSession(7, PARENT, True)
        self.assertEqual(self.coordinator.record_trusted_face(self.face(), 7).status, BridgeStatus.WRONG_ACCOUNT)
        self.assertEqual(self.coordinator.consume_for_logonui(7).status, BridgeStatus.NO_AUTHORIZATION)

    def test_wrong_session_consumption_invalidates(self):
        self.coordinator.record_trusted_face(self.face(), 7)
        self.assertEqual(self.coordinator.consume_for_logonui(8).status, BridgeStatus.WRONG_SESSION)
        self.assertEqual(self.coordinator.consume_for_logonui(7).status, BridgeStatus.NO_AUTHORIZATION)

    def test_os_session_id_mismatch_denies(self):
        self.session = WindowsSession(8, CHILD, True)
        self.assertEqual(self.coordinator.record_trusted_face(self.face(), 7).status, BridgeStatus.WRONG_SESSION)

    def test_unlocked_session_denies_both_phases(self):
        self.session = WindowsSession(7, CHILD, False)
        self.assertEqual(self.coordinator.record_trusted_face(self.face(), 7).status, BridgeStatus.UNLOCKED)
        self.session = WindowsSession(7, CHILD, True)
        self.coordinator.record_trusted_face(self.face(), 7)
        self.session = WindowsSession(7, CHILD, False)
        self.assertEqual(self.coordinator.consume_for_logonui(7).status, BridgeStatus.UNLOCKED)

    def test_quota_revocation_after_face_is_denied(self):
        self.coordinator.record_trusted_face(self.face(), 7)
        self.balances[1] = 0.0
        self.assertEqual(self.coordinator.consume_for_logonui(7).status,
                         BridgeStatus.REVOKED_OR_EXPIRED)

    def test_ticket_expiry(self):
        self.coordinator.record_trusted_face(self.face(), 7)
        self.clock[0] = 109
        self.assertEqual(self.coordinator.consume_for_logonui(7).status,
                         BridgeStatus.REVOKED_OR_EXPIRED)

    def test_new_observation_revokes_old_approval(self):
        self.coordinator.record_trusted_face(self.face(), 7)
        self.assertEqual(self.coordinator.record_trusted_face(self.face(2), 7).status,
                         BridgeStatus.EVIDENCE_DENIED)
        self.assertEqual(self.coordinator.consume_for_logonui(7).status,
                         BridgeStatus.NO_AUTHORIZATION)

    def test_invalid_face_never_issues_ticket(self):
        for face in (
            self.face(face_count=2),
            self.face(face_count=0),
            self.face(confirmations=1),
            self.face(live=False),
            self.face(observed_at=90),
            self.face(child_id=None),
            self.face(camera_ok=False),
        ):
            self.assertEqual(self.coordinator.record_trusted_face(face, 7).status,
                             BridgeStatus.EVIDENCE_DENIED)
            self.assertEqual(self.coordinator.consume_for_logonui(7).status,
                             BridgeStatus.NO_AUTHORIZATION)

    def test_camera_worker_disappears(self):
        self.coordinator.record_trusted_face(self.face(), 7)
        self.coordinator.invalidate()
        self.assertEqual(self.coordinator.consume_for_logonui(7).status,
                         BridgeStatus.NO_AUTHORIZATION)

    def test_account_switch_revokes(self):
        self.coordinator.record_trusted_face(self.face(), 7)
        self.session = WindowsSession(7, OTHER, True)
        self.assertEqual(self.coordinator.consume_for_logonui(7).status, BridgeStatus.WRONG_ACCOUNT)

    def test_reader_failure_denies(self):
        obj = OfflineUnlockCoordinator(
            target_sid=CHILD, parent_sid=PARENT,
            read_session=lambda _: (_ for _ in ()).throw(RuntimeError("WTS offline")),
            read_remaining=lambda _: 7000,
            clock=lambda: self.clock[0],
        )
        self.assertEqual(obj.record_trusted_face(self.face(), 7).status,
                         BridgeStatus.SERVICE_ERROR)
        self.balances.pop(1)
        self.assertEqual(self.coordinator.record_trusted_face(self.face(), 7).status,
                         BridgeStatus.SERVICE_ERROR)

    def test_invalid_or_same_sid_configuration(self):
        for invalid in ("", "Filhos", "S-1-5-18", "S-1-5-21-bad"):
            with self.assertRaises(ValueError):
                OfflineUnlockCoordinator(target_sid=invalid, parent_sid=PARENT,
                    read_session=lambda _: self.session, read_remaining=lambda _: 100)
        with self.assertRaises(ValueError):
            OfflineUnlockCoordinator(target_sid=CHILD, parent_sid=CHILD,
                read_session=lambda _: self.session, read_remaining=lambda _: 100)

    def test_fake_account_name_cannot_override_system_sid(self):
        self.session = WindowsSession(7, PARENT, True)
        self.assertEqual(self.coordinator.record_trusted_face(self.face(1), 7).status,
                         BridgeStatus.WRONG_ACCOUNT)

    def test_malformed_session_ids(self):
        for session in (True, "7", -1):
            self.assertEqual(self.coordinator.record_trusted_face(self.face(), session).status,
                             BridgeStatus.WRONG_SESSION)


if __name__ == "__main__":
    unittest.main()
