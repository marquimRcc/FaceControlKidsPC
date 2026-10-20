import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

import numpy as np

from facekids.broker import Broker, AccessDenied
from facekids.storage import Storage


def features(i):
    a = [0.0] * 128
    a[i] = 1.0
    return a


class BrokerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.db = Storage(Path(self.tmp.name) / "test.sqlite3")
        self.now = [0.0]
        self.broker = Broker(self.db, "PARENT", "CHILD", clock=lambda: self.now[0])

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_roles(self):
        with self.assertRaises(AccessDenied):
            self.broker.dispatch("CHILD", {"op": "bonus", "id": 1, "minutes": 15})
        with self.assertRaises(AccessDenied):
            self.broker.dispatch("OTHER", {"op": "status"})
        with self.assertRaises(ValueError):
            Broker(self.db, "SAME", "SAME")

    def test_parent_quota_operations(self):
        a = self.broker.dispatch("PARENT", {"op": "add", "name": "A", "minutes": 120})["id"]
        b = self.broker.dispatch("PARENT", {"op": "add", "name": "B", "minutes": 120})["id"]
        self.broker.dispatch("PARENT", {"op": "limit", "id": a, "minutes": 60})
        self.broker.dispatch("PARENT", {"op": "bonus", "id": b, "minutes": 15})
        self.assertEqual(self.db.remaining(a), 3600)
        self.assertEqual(self.db.remaining(b), 8100)

    def test_no_trust_in_client_supplied_elapsed_or_identity(self):
        kid = self.broker.dispatch("PARENT", {"op": "add", "name": "A", "minutes": 120})["id"]
        self.db.add_embedding(kid, np.asarray(features(0), dtype=np.float32))
        for t in (0, 5, 10):
            self.now[0] = t
            self.broker.dispatch("CHILD", {"op": "observe", "features": features(0),
                                            "seconds": 1_000_000, "id": 999})
        self.assertEqual(self.db.used(kid), 5)

    def test_enrollment_only_parent_and_sample_count(self):
        kid = self.broker.dispatch("PARENT", {"op": "add", "name": "A", "minutes": 120})["id"]
        with self.assertRaises(AccessDenied):
            self.broker.dispatch("CHILD", {"op": "enroll", "id": kid})
        self.broker.dispatch("PARENT", {"op": "enroll", "id": kid})
        result = {}
        for i in range(20):
            self.now[0] = i + 1.0
            result = self.broker.dispatch("CHILD", {"op": "observe", "features": features(0)})
        self.assertEqual(result["action"], "enrollment_complete")
        self.assertEqual(self.db.enrollment_count(kid), 20)

    def test_only_parent_can_erase_child_templates_and_revoke_enrollment(self):
        a = self.broker.dispatch("PARENT", {"op": "add", "name": "A", "minutes": 120})["id"]
        b = self.broker.dispatch("PARENT", {"op": "add", "name": "B", "minutes": 120})["id"]
        self.db.add_embedding(a, np.asarray(features(0), dtype=np.float32))
        self.db.add_embedding(a, np.asarray(features(0), dtype=np.float32))
        self.db.add_embedding(b, np.asarray(features(1), dtype=np.float32))
        self.broker.dispatch("PARENT", {"op": "enroll", "id": a})
        with self.assertRaises(AccessDenied):
            self.broker.dispatch("CHILD", {"op": "remove_faces", "id": a})
        self.assertEqual(self.db.enrollment_count(a), 2)
        deleted = self.broker.dispatch("PARENT", {"op": "remove_faces", "id": a})
        self.assertEqual(deleted, {"ok": True, "removed": 2})
        self.assertEqual(self.db.enrollment_count(a), 0)
        self.assertEqual(self.db.enrollment_count(b), 1)
        self.assertIsNone(self.broker.enroll_id)
        self.assertIsNone(self.broker.dispatch("CHILD", {"op": "ping"})["enrollment_id"])
        with self.assertRaises(ValueError):
            self.broker.dispatch("PARENT", {"op": "remove_faces", "id": True})

    def test_bad_vectors(self):
        with self.assertRaises(ValueError):
            self.broker.dispatch("CHILD", {"op": "observe", "features": [1.0] * 127})
        with self.assertRaises(ValueError):
            self.broker.dispatch("CHILD", {"op": "observe", "features": [True] * 128})

    def test_unknown_face_never_consumes(self):
        kid = self.broker.dispatch("PARENT", {"op": "add", "name": "A", "minutes": 120})["id"]
        self.db.add_embedding(kid, np.asarray(features(0), dtype=np.float32))
        for t in (0, 5, 10, 15, 20):
            self.now[0] = t
            self.broker.dispatch("CHILD", {"op": "observe", "features": None})
        self.assertEqual(self.db.used(kid), 0)


if __name__ == "__main__":
    unittest.main()
