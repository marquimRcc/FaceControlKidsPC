"""The experimental broker launcher never silently starts production services."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from facekids.quota_broker_lab import parse_args, validate_lab_options


class QuotaLabLauncherTests(unittest.TestCase):
    def options(self, path, *more):
        return parse_args([
            "--vm-lab-only", "--database", str(path),
            "--client-sid", "S-1-5-21-1000-2000-3000-1001",
            "--child-id", "1", "--pipe-suffix", "a" * 32, *more,
        ])

    def test_valid_lab_fixture_is_read_only_by_construction(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "facekids-quota-lab"
            root.mkdir()
            db = root / "fixture.sqlite3"
            db.write_bytes(b"synthetic placeholder")
            pipe, path, mapping = validate_lab_options(self.options(db))
            self.assertTrue(pipe.endswith("a" * 32))
            self.assertEqual(path, db.resolve())
            self.assertEqual(mapping, {"S-1-5-21-1000-2000-3000-1001": 1})
            self.assertEqual(db.read_bytes(), b"synthetic placeholder")

    def test_default_and_nonlab_sources_rejected(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            db = root / "criancas.sqlite3"
            db.write_bytes(b"dummy")
            with self.assertRaises(ValueError):
                validate_lab_options(self.options(db))
            lab = root / "facekids-quota-lab"
            lab.mkdir()
            fixture = lab / "fixture.sqlite3"
            fixture.write_bytes(b"dummy")
            no_opt = self.options(fixture)
            no_opt.vm_lab_only = False
            with self.assertRaises(ValueError):
                validate_lab_options(no_opt)
            for attr, bad in (
                ("client_sid", "Administrator"),
                ("client_sid", ""),
                ("client_sid", "S-1-5-21\n"),
                ("child_id", -1),
                ("child_id", 0),
                ("pipe_suffix", "Z" * 32),
                ("pipe_suffix", "../" + "a" * 32),
            ):
                obj = self.options(fixture)
                setattr(obj, attr, bad)
                with self.subTest(attr=attr, bad=bad), self.assertRaises(ValueError):
                    validate_lab_options(obj)


if __name__ == "__main__":
    unittest.main()
