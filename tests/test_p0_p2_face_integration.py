"""P0-P2: synthetic face and IPC contracts. No hardware or logon changes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
import time
import unittest

import numpy as np

from facekids.auth_service import FaceAuthenticator
from facekids.ipc_reply import validated_face_observation
from facekids.pipe_protocol import decode_pipe_command
from facekids.storage import Storage


class IntegratedFacePolicies(unittest.TestCase):
    def build(self, directory):
        path = Path(directory) / "synthetic.sqlite3"
        store = Storage(path)
        pid = store.add_person("Demo", 120)
        store.add_embedding(pid, np.ones(128, dtype=np.float32))
        store.close()
        rec = MagicMock()
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        video = MagicMock()
        video.isOpened.return_value = True
        video.read.return_value = True, frame
        return path, pid, rec, video

    def test_session_query_is_distinct_and_never_publishes_unlock_or_photo(self):
        self.assertEqual(decode_pipe_command(b"SESSION_QUERY\n"), ("SESSION_QUERY", None))
        with TemporaryDirectory() as folder:
            path, pid, rec, video = self.build(folder)
            rec.faces.return_value = [[5, 5, 80, 80]]
            rec.identify.return_value = (pid, 0.95)
            with patch("facekids.auth_service.cv2.VideoCapture", return_value=video), \
                 patch("pathlib.Path.write_text") as write_event, \
                 patch("facekids.auth_service.save_child_photo") as save:
                status, data = FaceAuthenticator(Path("models"), path, recognizer=rec).evaluate(
                    publish_unlock_event=False)
            self.assertEqual(status, "ALLOW")
            self.assertEqual(data["child_id"], pid)
            write_event.assert_not_called()
            save.assert_not_called()

    def test_smaller_recognized_face_owns_its_photo_crop(self):
        with TemporaryDirectory() as folder:
            path, pid, rec, video = self.build(folder)
            big = [0, 0, 150, 150]
            small = [40, 40, 45, 45]
            rec.faces.return_value = [big, small]
            rec.identify.side_effect = [(None, 0.1), (pid, 0.95)] * 2
            with patch("facekids.auth_service.cv2.VideoCapture", return_value=video), \
                 patch("facekids.avatar_utils.get_child_avatar_path", return_value=None), \
                 patch("facekids.auth_service.save_child_photo") as save:
                status, data = FaceAuthenticator(Path("models"), path, recognizer=rec).evaluate()
            self.assertEqual(status, "ALLOW")
            self.assertEqual(data["child_id"], pid)
            self.assertEqual(data["face_count"], 2)
            self.assertEqual(save.call_args.args[2], small)

    def test_deny_is_strictly_validated_before_lock(self):
        now = time.time()
        reply = dict(status="DENY_QUOTA", protocol_marker="FACEKIDS_IPC_V1",
                     child_id=2, child_name="Demo", remaining=0, timestamp=now,
                     data=dict(child_id=2, child_name="Demo", remaining=0,
                               detected_ids=[2], face_count=1))
        valid = validated_face_observation(reply, now=now)
        self.assertIsNotNone(valid)
        self.assertEqual(valid.status, "DENY_QUOTA")
        mutations = [
            {"timestamp": now - 25}, {"child_id": 9}, {"remaining": 1},
            {"protocol_marker": "bogus"},
            {"data": {**reply["data"], "face_count": 2, "detected_ids": [2, 2]}},
            {"data": {**reply["data"], "detected_ids": [99]}},
            {"data": {**reply["data"], "face_count": True}},
        ]
        for changes in mutations:
            with self.subTest(changes=changes):
                self.assertIsNone(validated_face_observation(
                    {**reply, **changes}, now=now))


if __name__ == "__main__":
    unittest.main()
