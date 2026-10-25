"""Tests for all three UI palettes and safe per-parent persistence.

No GUI, Windows account, webcam, credential provider or family SQLite used.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from facekids.ui_theme import (
    DEFAULT_THEME, THEMES, load_theme, preference_path, save_theme,
    theme_palette,
)


class ThemeChoiceTests(unittest.TestCase):
    def test_exactly_three_named_themes_and_original_palette_unchanged(self):
        self.assertEqual(tuple(THEMES), ("Atual", "Claro", "Escuro"))
        self.assertEqual(DEFAULT_THEME, "Atual")
        original = theme_palette("Atual")
        self.assertEqual(original["BG_MAIN"], "#0F0F17")
        self.assertEqual(original["BG_HEADER"], "#181825")
        self.assertEqual(original["ACCENT_BLUE"], "#38BDF8")
        self.assertEqual(original["TEXT_TITLE"], "#CDD6F4")
        self.assertEqual(original["BG_FIELD"], "#11111B")
        self.assertEqual(original["TEXT_ON_ACCENT"], "#0B0B12")

    def test_palette_has_same_roles_and_distinct_theme_colors(self):
        expected = set(THEMES["Atual"])
        for name in THEMES:
            palette = theme_palette(name)
            self.assertEqual(set(palette), expected)
            for role, color in palette.items():
                with self.subTest(theme=name, role=role):
                    self.assertRegex(color, r"^#[0-9A-Fa-f]{6}$")
        self.assertEqual(THEMES["Claro"]["BG_HEADER"], "#FFFFFF")
        self.assertNotEqual(THEMES["Claro"]["BG_MAIN"], THEMES["Escuro"]["BG_MAIN"])
        self.assertNotEqual(THEMES["Escuro"]["BG_MAIN"], THEMES["Atual"]["BG_MAIN"])
        copy = theme_palette("Atual")
        copy["BG_MAIN"] = "#ABCDEF"
        self.assertEqual(theme_palette("Atual")["BG_MAIN"], "#0F0F17")

    def test_reject_unknown_theme_before_writing_any_files(self):
        with TemporaryDirectory() as root:
            destination = Path(root) / "not-created" / "settings.json"
            for candidate in ("Preto", "", "../Claro", None, 0):
                with self.subTest(candidate=candidate):
                    with self.assertRaises(ValueError):
                        save_theme(candidate, path=destination)
                    self.assertFalse(destination.parent.exists())

    def test_atomic_choice_survives_restarts_for_all_three_themes(self):
        with TemporaryDirectory() as root:
            file = Path(root) / "parent-only" / "appearance.json"
            self.assertEqual(load_theme(path=file), "Atual")
            for name in THEMES:
                save_theme(name, path=file)
                self.assertEqual(load_theme(path=file), name)
                self.assertEqual(json.loads(file.read_text(encoding="utf-8")),
                                 {"version": 1, "theme": name})
                self.assertEqual(sorted(file.parent.iterdir()), [file])

    def test_invalid_or_corrupt_preference_falls_back_to_original(self):
        with TemporaryDirectory() as root:
            file = Path(root) / "appearance.json"
            for invalid in (
                "invalid json", "null", "[]", "{}", '{"theme": "Claro"}',
                '{"version": 1, "theme": "Other"}',
                '{"version": 1, "theme": null}',
            ):
                with self.subTest(payload=invalid):
                    file.write_text(invalid, encoding="utf-8")
                    self.assertEqual(load_theme(path=file), "Atual")

    def test_preference_location_is_never_inside_child_programdata(self):
        with TemporaryDirectory() as root:
            expected = Path(root) / "FaceKids" / "parent-ui-preferences.json"
            self.assertEqual(preference_path(base=Path(root)), expected)


if __name__ == "__main__":
    unittest.main()
