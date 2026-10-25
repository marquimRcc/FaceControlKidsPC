"""Headless UI regression tests: no webcam, Windows logon or Tk display."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from facekids.parent_ui_state import (
    filter_children, load_overview, screen_time_label, validate_schedule
)
from facekids.storage import Storage


class ParentsOverviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.store = Storage(Path(self.temp.name) / "synthetic-ui.sqlite3")
        self.ana = self.store.add_person("Ana", 120)
        self.joao = self.store.add_person("João Pedro", 90)
        self.bia = self.store.add_person("Bia", 60)
        self.store.add_embedding(self.ana, np.ones(128, dtype=np.float32))
        self.store.add_embedding(self.bia, np.ones(128, dtype=np.float32))
        self.store.charge(self.ana, 30 * 60, "2026-10-25")
        self.store.charge(self.joao, 90 * 60, "2026-10-25")
        self.store.add_bonus(self.ana, 15, "2026-10-25")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_three_children_quota_progress_and_biometrics(self):
        dashboard = load_overview(self.store, day="2026-10-25")
        self.assertEqual(dashboard.total_children, 3)
        self.assertEqual(dashboard.recognized_children, 2)
        self.assertEqual(dashboard.pending_children, 1)
        ana, joao, bia = dashboard.children
        self.assertEqual(ana.remaining_seconds, 105 * 60)
        self.assertEqual(ana.total_seconds, 135 * 60)
        self.assertAlmostEqual(ana.remaining_fraction, 105 / 135)
        self.assertEqual(ana.bonus_minutes, 15)
        self.assertEqual(joao.status_text, "Rosto pendente")
        self.assertEqual(joao.remaining_fraction, 0)
        self.assertEqual(bia.status_text, "Biometria cadastrada")
        self.assertEqual(dashboard.remaining_seconds, (105 + 60) * 60)

    def test_accent_insensitive_search_and_status_updates(self):
        overview = load_overview(self.store, day="2026-10-25")
        found = filter_children(overview.children, "JOAO")
        self.assertEqual([child.child_id for child in found], [self.joao])
        self.assertEqual(len(filter_children(overview.children, "")), 3)
        self.assertEqual(len(filter_children(overview.children, "inexistente")), 0)
        self.assertEqual(len(filter_children(overview.children, str(self.ana))), 1)
        self.store.add_embedding(self.joao, np.ones(128, dtype=np.float32))
        refreshed = load_overview(self.store, day="2026-10-25")
        self.assertEqual(refreshed.children[1].status_text, "Tempo esgotado")

    def test_schedule_preview_is_explicit_and_read_only(self):
        self.store.set_curfew_config(True, "08:00", "20:00")
        within = load_overview(self.store, day="2026-10-25", current_time="09:00")
        outside = load_overview(self.store, day="2026-10-25", current_time="21:00")
        self.assertEqual(within.schedule_text, "08:00–20:00")
        self.assertFalse(within.outside_schedule)
        self.assertTrue(outside.outside_schedule)
        self.store.set_curfew_config(False, "08:00", "20:00")
        disabled = load_overview(self.store, day="2026-10-25", current_time="21:00")
        self.assertFalse(disabled.outside_schedule)
        self.assertEqual(disabled.schedule_text, "Sem horário configurado")

    def test_inline_schedule_rejects_malformed_and_ambiguous_values(self):
        self.assertEqual(validate_schedule(True, " 08:00 ", "20:00"),
                         (True, "08:00", "20:00"))
        self.assertEqual(validate_schedule(False, "08:00", "08:00"),
                         (False, "08:00", "08:00"))
        for enabled, start, end in (
            (True, "08:00", "08:00"),
            (True, "24:00", "20:00"),
            (True, "08:60", "20:00"),
            (True, "8:00", "20:00"),
            (True, "08:00", ""),
            ("true", "08:00", "20:00"),
        ):
            with self.subTest(enabled=enabled, start=start, end=end):
                with self.assertRaises(ValueError):
                    validate_schedule(enabled, start, end)

    def test_formatting(self):
        self.assertEqual(screen_time_label(0), "0 min")
        self.assertEqual(screen_time_label(-4), "0 min")
        self.assertEqual(screen_time_label(7199), "1h 59min")


if __name__ == "__main__":
    unittest.main()
