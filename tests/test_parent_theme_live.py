"""Tk-free state transition tests for live parent dashboard theme switching."""
import unittest
from unittest.mock import Mock, patch

from facekids import admin_dashboard


class FakeVariable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeDashboard:
    def __init__(self):
        self.theme_name = "Atual"
        self.theme_var = FakeVariable("Atual")
        self.search_var = FakeVariable("João")
        self.schedule_enabled_var = FakeVariable(True)
        self.schedule_start_var = FakeVariable("09:15")
        self.schedule_end_var = FakeVariable("19:45")
        self._schedule_loaded = (True, "08:00", "20:00")
        self.db = Mock()
        self.store = Mock()
        self.avatar_images = {4: object()}
        self.old_widget = Mock()
        self._build_ui_called = 0
        self.refreshed = 0
        self.hidden = False
        self.visible = True
        self.configured_colors = []
        self.status_text = FakeVariable("")

    def winfo_children(self):
        return [self.old_widget]

    def withdraw(self):
        self.hidden = True
        self.visible = False

    def deiconify(self):
        self.hidden = False
        self.visible = True

    def configure(self, **kwargs):
        self.configured_colors.append(kwargs)

    def _build_ui(self):
        self._build_ui_called += 1
        self.theme_var = FakeVariable(self.theme_name)
        self.search_var = FakeVariable("")
        self.schedule_enabled_var = FakeVariable(False)
        self.schedule_start_var = FakeVariable("08:00")
        self.schedule_end_var = FakeVariable("20:00")
        self._schedule_loaded = None
        self.status_text = FakeVariable("")

    def refresh(self):
        self.refreshed += 1


class LiveThemeTests(unittest.TestCase):
    def tearDown(self):
        admin_dashboard._activate_theme("Atual")

    def test_all_three_transitions_rebuild_gui_and_preserve_unsaved_edits(self):
        ui = FakeDashboard()
        with patch.object(admin_dashboard, "save_theme") as save:
            for index, target in enumerate(("Claro", "Escuro", "Atual"), 1):
                admin_dashboard.AdminDashboard._change_theme(ui, target)
                self.assertEqual(ui.theme_name, target)
                self.assertEqual(ui._build_ui_called, index)
                self.assertTrue(ui.visible)
                self.assertEqual(ui.search_var.get(), "João")
                self.assertEqual(ui.schedule_enabled_var.get(), True)
                self.assertEqual(ui.schedule_start_var.get(), "09:15")
                self.assertEqual(ui.schedule_end_var.get(), "19:45")
                self.assertEqual(ui._schedule_loaded, (True, "08:00", "20:00"))
                self.assertEqual(ui.status_text.get(), f"Tema {target} aplicado e salvo.")
                self.assertEqual(ui.configured_colors[-1]["bg"],
                                 admin_dashboard.theme_palette(target)["BG_MAIN"])
                self.assertEqual(ui.refreshed, index)
            self.assertEqual([call.args[0] for call in save.call_args_list],
                             ["Claro", "Escuro", "Atual"])
            self.assertEqual(ui.old_widget.destroy.call_count, 3)
            ui.store.set_setting.assert_not_called()
            ui.store.set_curfew_config.assert_not_called()
            ui.db.close.assert_not_called()

    def test_save_failure_leaves_original_palette_and_keeps_current_ui(self):
        ui = FakeDashboard()
        ui.theme_var.set("Claro")
        with patch.object(admin_dashboard, "save_theme",
                          side_effect=PermissionError("no access")), patch.object(
                              admin_dashboard.messagebox, "showerror"
                          ) as dialog:
            admin_dashboard.AdminDashboard._change_theme(ui, "Claro")
        self.assertEqual(ui.theme_name, "Atual")
        self.assertEqual(ui.theme_var.get(), "Atual")
        self.assertEqual(ui._build_ui_called, 0)
        self.assertEqual(admin_dashboard.BG_MAIN, "#0F0F17")
        self.assertTrue(ui.visible)
        dialog.assert_called_once()

    def test_noop_does_not_change_ui_or_touch_disk(self):
        ui = FakeDashboard()
        with patch.object(admin_dashboard, "save_theme") as save:
            admin_dashboard.AdminDashboard._change_theme(ui, "Atual")
        save.assert_not_called()
        self.assertEqual(ui._build_ui_called, 0)
        self.assertEqual(ui.refreshed, 0)


if __name__ == "__main__":
    unittest.main()
