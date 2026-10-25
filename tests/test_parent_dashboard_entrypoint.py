"""Headless smoke test of the ACTUAL BAT-launched Windows parent dashboard."""
import inspect
from pathlib import Path
import unittest

from facekids import admin_dashboard
from facekids.parent_ui_state import filter_children, load_overview, validate_schedule


class ParentDashboardEntrypointTests(unittest.TestCase):
    def test_bat_launches_the_modernized_parent_dashboard(self):
        root = Path(__file__).resolve().parents[1]
        launcher = (root / "abrir-facekids.bat").read_text(encoding="utf-8")
        self.assertIn("-m facekids.admin_dashboard", launcher)
        self.assertTrue(callable(admin_dashboard.main))
        self.assertTrue(issubclass(admin_dashboard.AdminDashboard, admin_dashboard.tk.Tk))

    def test_inline_schedule_search_and_overview_have_actual_ui_handlers(self):
        cls = admin_dashboard.AdminDashboard
        self.assertTrue(callable(cls._save_inline_schedule))
        self.assertTrue(callable(cls.refresh))
        self.assertTrue(callable(cls._create_child_card))
        self.assertIn("validate_schedule", inspect.getsource(cls._save_inline_schedule))
        self.assertIn("filter_children", inspect.getsource(cls.refresh))
        self.assertIn("load_overview", inspect.getsource(cls.refresh))
        self.assertEqual(validate_schedule(True, "08:00", "20:00"),
                         (True, "08:00", "20:00"))

    def test_import_smoke_does_not_require_a_display(self):
        # Only inspect class and module; do not instantiate a Tk root.
        self.assertEqual(admin_dashboard.AdminDashboard.__module__,
                         "facekids.admin_dashboard")
        self.assertTrue(callable(filter_children))
        self.assertTrue(callable(load_overview))


if __name__ == "__main__":
    unittest.main()
