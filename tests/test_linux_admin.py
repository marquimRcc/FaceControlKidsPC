import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from facekids.linux_admin import main
from facekids.storage import Storage


class LinuxAdminTests(unittest.TestCase):
    def test_setup_limits_bonus_and_curfew(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "kids.sqlite3"
            base = ["--database", str(database)]
            self.assertEqual(main(base + ["setup"]), 0)
            self.assertEqual(main(base + ["set-limit", "1", "90"]), 0)
            self.assertEqual(main(base + ["bonus", "1", "30"]), 0)
            self.assertEqual(main(base + ["curfew", "08:00", "20:00"]), 0)
            store = Storage(database)
            try:
                first = store.people()[0][0]
                self.assertEqual(store.remaining(first), 120 * 60)
                self.assertEqual(store.get_curfew_config(), (True, "08:00", "20:00"))
            finally:
                store.close()

    def test_invalid_curfew_is_not_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "kids.sqlite3"
            base = ["--database", str(database)]
            main(base + ["setup"])
            with self.assertRaises(ValueError):
                main(base + ["curfew", "99:00", "20:00"])
            store = Storage(database)
            try:
                self.assertFalse(store.get_curfew_config()[0])
            finally:
                store.close()

    @patch("builtins.print")
    def test_status_has_exactly_three_profiles(self, printer):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "kids.sqlite3"
            main(["--database", str(database), "status"])
            status_lines = [call for call in printer.call_args_list if "amostras=" in str(call)]
            self.assertEqual(len(status_lines), 3)


if __name__ == "__main__":
    unittest.main()
