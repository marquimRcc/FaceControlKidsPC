"""Regression contract for main session behavior + staged service quota writer.

Synthetic IDs/bytes only. Never exercises webcam, LogonUI, Windows login
or the family database. Preserving source expressions alone does not prove
real-world correctness; these guards stop accidental replacement of the
established domestic agent while the new broker is VM-only.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from facekids import filhos_agent, auth_service
from facekids.storage import Storage


class DeveloperIntegrationRegression(unittest.TestCase):
    def test_main_session_rules_use_the_real_pure_policy(self):
        source = inspect.getsource(filhos_agent.run_agent)
        from facekids.session_transition_policy import (
            decide_child_transition, TransitionDecision)
        self.assertIn("decide_child_transition(", source)
        self.assertIn("session_active_since_mono", source)
        self.assertIn("idle_sec = min(get_user_idle_seconds(), active_duration)", source)
        self.assertIn("store.refund(", source)
        self.assertIn("quota_accounting.active_tick", source)
        self.assertIn('command="SESSION_QUERY"', inspect.getsource(
            filhos_agent.InSessionFaceIdentifier.trigger_if_due))
        self.assertNotIn("store.charge(", source)
        self.assertNotIn("BrokerLabReadOnlyQuota(", source)
        # UI notification file cannot drive quota ownership or inactivity.
        start = source.index("# Notification file is UI-only")
        end = source.index("# B. Checar", start)
        untrusted = source[start:end]
        self.assertNotIn("tracker.switch_child(", untrusted)
        self.assertNotIn("session_active_since_mono =", untrusted)
        self.assertEqual(
            decide_child_transition(7, [7, 8], 2, 25, 8,
                                    observation_age_seconds=0),
            TransitionDecision.KEEP_CURRENT)
        self.assertEqual(
            decide_child_transition(7, [8], 1, 25, 8,
                                    observation_age_seconds=0),
            TransitionDecision.SWITCH_CHILD)

    def test_multi_face_response_contract_keeps_metadata(self):
        source = inspect.getsource(auth_service.FaceAuthenticator.evaluate)
        for field in ("detected_ids", "face_count"):
            self.assertIn(field, source)

    def test_main_photo_and_idle_refund_survive_broker_writer_cutover(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.sqlite3"
            with_photos = Storage(path)
            try:
                person = with_photos.add_person("Test profile", 120)
                jpeg = b"\xff\xd8" + b"Z" * 125 + b"\xff\xd9"
                with with_photos.db:
                    with_photos.db.execute(
                        "INSERT INTO profile_photos(person_id,jpeg,selected) VALUES(?,?,1)",
                        (person, jpeg),
                    )
                day = "2026-10-27"
                with_photos.charge(person, 120, day)
                self.assertEqual(with_photos.refund(person, 120, day), 0)
                self.assertEqual(with_photos.used(person, day), 0)
                self.assertEqual(with_photos.selected_profile_photo(person), jpeg)

                with_photos.set_setting("quota_writer_owner", "vm-service-only")
                with self.assertRaises(PermissionError):
                    with_photos.charge(person, 10, day)
                with self.assertRaises(PermissionError):
                    with_photos.refund(person, 10, day)
                self.assertEqual(
                    with_photos.charge_capped_once("1" * 32, person, 10, day), 10
                )
                self.assertEqual(
                    with_photos.charge_capped_once("1" * 32, person, 10, day), 0
                )
                self.assertEqual(with_photos.used(person, day), 10)
                self.assertEqual(with_photos.selected_profile_photo(person), jpeg)
            finally:
                with_photos.close()

            after_restart = Storage(path)
            try:
                self.assertEqual(after_restart.used(person, day), 10)
                self.assertEqual(after_restart.selected_profile_photo(person), jpeg)
                with self.assertRaises(PermissionError):
                    after_restart.charge(person, 1, day)
            finally:
                after_restart.close()


if __name__ == "__main__":
    unittest.main()
