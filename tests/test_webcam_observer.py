import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np

from facekids.webcam_observer import WebcamObserver, classify_face_sample, load_enrollments
from facekids.storage import Storage


class ObserverUnitTest(unittest.TestCase):
    def test_observation_classification(self):
        self.assertIsNone(classify_face_sample(0, None))
        self.assertEqual(classify_face_sample(1, None), "unknown")
        self.assertEqual(classify_face_sample(2, 1), "multiple")
        self.assertEqual(classify_face_sample(1, 7), 7)
        with self.assertRaises(ValueError):
            classify_face_sample(1, True)

    def test_read_only_existing_profiles(self):
        with TemporaryDirectory() as temp:
            filename = Path(temp) / "family.sqlite3"
            db = Storage(filename)
            first = db.add_person("Filho 1", 120)
            second = db.add_person("Filho 2", 120)
            vec = np.zeros(128, dtype=np.float32)
            vec[0] = 1.0
            db.add_embedding(first, vec)
            db.charge(first, 1800)
            db.add_bonus(second, 15)
            db.close()
            loaded = load_enrollments(filename)
            self.assertEqual(loaded.names[first], "Filho 1")
            self.assertEqual(loaded.balances[first], 5400)
            self.assertEqual(loaded.balances[second], 8100)
            self.assertEqual(loaded.unenrolled, ("Filho 2",))
            self.assertEqual(len(loaded.embeddings), 1)
            self.assertTrue(filename.is_file())

    def test_missing_db_does_not_create_anything(self):
        with TemporaryDirectory() as temp:
            file = Path(temp) / "nonexistent.sqlite3"
            with self.assertRaises(FileNotFoundError):
                load_enrollments(file)
            self.assertFalse(file.exists())

    def test_reject_no_embedding(self):
        with TemporaryDirectory() as temp:
            filename = Path(temp) / "db.sqlite3"
            db = Storage(filename)
            db.add_person("Filho", 120)
            db.close()
            with self.assertRaises(ValueError):
                load_enrollments(filename)

    def test_invalid_camera_options(self):
        with self.assertRaises(ValueError):
            WebcamObserver(Path("."), [], camera_index=-1)
        with self.assertRaises(ValueError):
            WebcamObserver(Path("."), [], interval=0.1)


if __name__ == "__main__":
    unittest.main()
