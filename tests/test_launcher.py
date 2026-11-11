"""Testes do inicializador unificado e Smart Launcher do SafePCKids."""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from safepckids.launcher import is_system_installed, main, admin_main, installer_main


class TestLauncher(unittest.TestCase):
    def test_is_system_installed_false_when_db_missing(self):
        with patch("safepckids.launcher.DEFAULT_DB_FILE", Path("non_existent_file.sqlite3")):
            self.assertFalse(is_system_installed())

    def test_is_system_installed_true_when_db_and_people_exist(self):
        with patch("safepckids.launcher.DEFAULT_DB_FILE") as mock_db, \
             patch("safepckids.launcher.INSTALL_MARKER") as mock_marker, \
             patch("safepckids.launcher.Storage") as mock_storage_cls:
            mock_db.exists.return_value = True
            mock_marker.exists.return_value = True
            mock_store = MagicMock()
            mock_store.get_setting.return_value = "pbkdf2_sha256:..."
            mock_store.people.return_value = [(1, "Filho", 7200)]
            mock_store.embeddings.return_value = [(1, "vector")]
            mock_storage_cls.return_value = mock_store

            self.assertTrue(is_system_installed())

    def test_is_system_installed_true_without_children(self):
        with patch("safepckids.launcher.DEFAULT_DB_FILE") as mock_db, \
             patch("safepckids.launcher.INSTALL_MARKER") as mock_marker, \
             patch("safepckids.launcher.Storage") as mock_storage_cls:
            mock_db.exists.return_value = True
            mock_marker.exists.return_value = True
            mock_store = MagicMock()
            mock_store.get_setting.return_value = "pbkdf2_sha256:..."
            mock_store.people.return_value = []
            mock_store.embeddings.return_value = []
            mock_storage_cls.return_value = mock_store

            self.assertTrue(is_system_installed())

    @patch("safepckids.launcher.open_app_window", return_value=0)
    @patch("safepckids.launcher.ensure_admin_if_needed")
    def test_main_routes_to_dashboard_with_admin_flag(self, mock_ensure, mock_open):
        res = main(["--admin"])
        self.assertEqual(res, 0)
        mock_open.assert_called_once_with(mode="dashboard")

    @patch("safepckids.launcher.open_app_window", return_value=0)
    @patch("safepckids.launcher.ensure_admin_if_needed")
    def test_main_routes_to_wizard_with_setup_flag(self, mock_ensure, mock_open):
        res = main(["--setup"])
        self.assertEqual(res, 0)
        mock_open.assert_called_once_with(mode="wizard")

    @patch("safepckids.launcher.open_app_window", return_value=0)
    @patch("safepckids.launcher.ensure_admin_if_needed")
    @patch("safepckids.launcher.is_system_installed", return_value=True)
    def test_smart_launcher_picks_dashboard_when_installed(self, mock_installed, mock_ensure, mock_open):
        res = main([])
        self.assertEqual(res, 0)
        mock_open.assert_called_once_with(mode="dashboard")

    @patch("safepckids.launcher.open_app_window", return_value=0)
    @patch("safepckids.launcher.ensure_admin_if_needed")
    @patch("safepckids.launcher.is_system_installed", return_value=False)
    def test_smart_launcher_picks_wizard_when_not_installed(self, mock_installed, mock_ensure, mock_open):
        res = main([])
        self.assertEqual(res, 0)
        mock_open.assert_called_once_with(mode="wizard")

    @patch("safepckids.launcher.main", return_value=0)
    def test_convenience_functions(self, mock_main):
        admin_main()
        mock_main.assert_called_with(["--admin"])

        installer_main()
        mock_main.assert_called_with(["--setup"])


if __name__ == "__main__":
    unittest.main()
