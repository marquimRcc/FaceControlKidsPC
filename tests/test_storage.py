import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from facekids.storage import Storage

class StorageTest(unittest.TestCase):
    def test_user_independent_usage_and_daily_reset(self):
        with TemporaryDirectory() as d:
            db=Storage(Path(d)/"test.sqlite3")
            a=db.add_person("A",120)
            b=db.add_person("B",120)
            db.charge(a,61,"2026-10-19")
            self.assertEqual(db.remaining(a,"2026-10-19"),7139)
            self.assertEqual(db.remaining(b,"2026-10-19"),7200)
            self.assertEqual(db.remaining(a,"2026-10-20"),7200)
            db.add_embedding(a,np.ones(128,dtype=np.float32))
            self.assertEqual(db.embeddings()[0][0],a)
            db.close()
