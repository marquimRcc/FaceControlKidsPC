"""GitHub-hosted Windows Tk smoke: exercise the real theme option menu.

Never runs on the family PC or modifies Windows logon. Creates synthetic
profiles and a disposable parent-theme setting. Uses the real Tk event menu
callback so widget destruction/rebuild bugs are detectable.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch

from facekids import admin_dashboard
from facekids.storage import Storage
from facekids.ui_theme import load_theme, save_theme, theme_palette


def _require_hosted_windows() -> None:
    expected = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Windows",
        "GITHUB_REPOSITORY": "marquimRcc/FaceControlKidsPC",
    }
    if os.name != "nt" or any(os.environ.get(key) != value
                              for key, value in expected.items()):
        raise RuntimeError("Theme GUI smoke runs only on disposable GitHub-hosted Windows")


def _find_option_menu(parent):
    for widget in parent.winfo_children():
        if isinstance(widget, tk.OptionMenu):
            return widget
        found = _find_option_menu(widget)
        if found is not None:
            return found
    return None


def main() -> int:
    _require_hosted_windows()
    with tempfile.TemporaryDirectory(prefix="facekids-parent-ui-smoke-") as folder:
        path = Path(folder) / "synthetic-children.sqlite3"
        pref = Path(folder) / "preferences" / "theme.json"
        db = Storage(path)
        try:
            for index in range(3):
                db.add_person(f"Filho sintético {index + 1}", 120)
        finally:
            db.close()

        try:
            probe = tk.Tk()
            probe.withdraw()
            probe.destroy()
        except tk.TclError as exc:
            # Some Windows agents intentionally have no graphical desktop.
            print(f"SKIP: no Tk display on disposable runner: {type(exc).__name__}")
            return 0

        app = None
        with patch.object(admin_dashboard, "is_admin_account", return_value=True), \
             patch.object(admin_dashboard, "child_pilot_database", return_value=path), \
             patch.object(admin_dashboard, "load_theme", return_value="Atual"), \
             patch.object(admin_dashboard, "save_theme", side_effect=lambda name: save_theme(name, path=pref)), \
             patch.object(admin_dashboard, "get_child_avatar_path", return_value=None):
            try:
                app = admin_dashboard.AdminDashboard()
                app.withdraw()
                app.update_idletasks()
                if app.theme_name != "Atual":
                    raise AssertionError("Incorrect initial theme")
                app.search_var.set("sintético")
                app.schedule_enabled_var.set(True)
                app.schedule_start_var.set("09:15")
                app.schedule_end_var.set("19:45")

                for index, name in ((1, "Claro"), (2, "Escuro"), (0, "Atual")):
                    menu = _find_option_menu(app)
                    if menu is None:
                        raise AssertionError("The actual theme chooser was not created")
                    # Execute real Tcl menu command, not the Python handler directly.
                    menu["menu"].invoke(index)
                    app.update_idletasks()
                    if app.theme_name != name or load_theme(path=pref) != name:
                        raise AssertionError(f"Theme choice not applied/persisted: {name}")
                    if app.cget("background").lower() != theme_palette(name)["BG_MAIN"].lower():
                        raise AssertionError("Root window did not change background")
                    if app.search_var.get() != "sintético":
                        raise AssertionError("Theme change erased unsaved child search")
                    if (app.schedule_start_var.get(), app.schedule_end_var.get()) != (
                        "09:15", "19:45"
                    ):
                        raise AssertionError("Theme change erased unsaved allowed hours")
                    if len(app.store.people()) != 3:
                        raise AssertionError("Theme change altered synthetic child profiles")
                print("PASS: actual Tk menu switched all three palettes and persisted choice")
                return 0
            finally:
                if app is not None and app.winfo_exists():
                    app.destroy()

if __name__ == "__main__":
    raise SystemExit(main())
