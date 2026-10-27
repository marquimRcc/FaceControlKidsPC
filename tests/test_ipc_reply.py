"""Synthetic in-session authorization tests, no camera or Windows login."""
import math
import time
import unittest

from facekids.ipc_reply import validated_pipe_allow


class IPCReplyTests(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.valid = {
            "status": "ALLOW",
            "user": "Filhos",
            "protocol_marker": "FACEKIDS_IPC_V1",
            "child_id": 2,
            "child_name": "Crianca 2",
            "remaining": 7199,
            "timestamp": self.now,
        }

    def test_accept_complete_fresh_reply(self):
        self.assertEqual(
            validated_pipe_allow(self.valid, now=self.now),
            (2, "Crianca 2", self.now)
        )

    def test_reject_missing_or_spoofed_identity(self):
        for name, value in (
            ("user", "Administrator"),
            ("user", None),
            ("protocol_marker", "WRONG"),
            ("status", "DENY_QUOTA"),
            ("child_id", 0),
            ("child_id", True),
            ("child_id", "2"),
            ("child_name", ""),
        ):
            with self.subTest(name=name, value=value):
                self.assertIsNone(validated_pipe_allow({**self.valid, name: value}, now=self.now))

    def test_reject_exhausted_or_nonfinite_quota(self):
        for remaining in (0, -1, float("nan"), float("inf"), None, "7200", True):
            with self.subTest(remaining=str(remaining)):
                self.assertIsNone(validated_pipe_allow(
                    {**self.valid, "remaining": remaining}, now=self.now
                ))

    def test_reject_stale_future_or_invalid_timestamps(self):
        for ts in (self.now - 20, self.now + 20, float("nan"), float("inf"), "123", True):
            with self.subTest(ts=str(ts)):
                self.assertIsNone(validated_pipe_allow(
                    {**self.valid, "timestamp": ts}, now=self.now
                ))

    def test_untrusted_payload_is_not_authenticated_by_marker(self):
        # A syntactically valid marker is NOT cryptographic authenticity.
        self.assertIsNone(validated_pipe_allow(None, now=self.now))
        self.assertIsNone(validated_pipe_allow([], now=self.now))


if __name__ == "__main__":
    unittest.main()
