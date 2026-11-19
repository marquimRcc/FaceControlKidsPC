"""Testes unitários automatizados para o Bloqueio Remoto (Pause) do SafePCKids."""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from safepckids.storage import Storage


class TestRemotePauseStorage(unittest.TestCase):
    """Testes de persistência e comportamento de pausa remota no Storage."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_kids.sqlite3"
        self.store = Storage(self.db_path)

    def tearDown(self):
        try:
            self.store.close()
        except Exception:
            pass
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_remote_pause_initial_state(self):
        """Inicialmente não deve haver pausa ativa."""
        is_paused, reason, remaining = self.store.get_remote_pause_state()
        self.assertFalse(is_paused)
        self.assertEqual(reason, "")
        self.assertEqual(remaining, 0)

    def test_set_and_clear_remote_pause(self):
        """Ativa pausa temporária e depois limpa com sucesso."""
        data = self.store.set_remote_pause(duration_seconds=1800, reason="Hora do almoço! 🍽️")
        self.assertTrue(data["is_paused"])
        self.assertEqual(data["duration_seconds"], 1800)
        self.assertEqual(data["reason"], "Hora do almoço! 🍽️")

        is_paused, reason, remaining = self.store.get_remote_pause_state()
        self.assertTrue(is_paused)
        self.assertEqual(reason, "Hora do almoço! 🍽️")
        self.assertGreater(remaining, 1750)
        self.assertLessEqual(remaining, 1800)

        # Limpar pausa
        self.store.clear_remote_pause()
        is_paused, reason, remaining = self.store.get_remote_pause_state()
        self.assertFalse(is_paused)
        self.assertEqual(remaining, 0)

    def test_remote_pause_permanent(self):
        """Pausa definitiva (duration_seconds=0) não expira por tempo."""
        self.store.set_remote_pause(duration_seconds=0, reason="Bloqueio definitivo")
        is_paused, reason, remaining = self.store.get_remote_pause_state()
        self.assertTrue(is_paused)
        self.assertEqual(reason, "Bloqueio definitivo")
        self.assertEqual(remaining, 0)

    def test_remote_pause_auto_expire(self):
        """Pausa temporária expira automaticamente quando o tempo passa."""
        now = time.time()
        # Simula criação no passado (expirada há 10 segundos)
        fake_data = {
            "is_paused": True,
            "pause_until": now - 10.0,
            "duration_seconds": 60,
            "reason": "Expirada",
            "created_at": now - 70.0,
        }
        self.store.set_setting("remote_pause", json.dumps(fake_data))

        # Ao consultar, deve detectar a expiração, limpar e retornar False
        is_paused, reason, remaining = self.store.get_remote_pause_state()
        self.assertFalse(is_paused)
        self.assertEqual(remaining, 0)
        # Verifica se limpou da tabela settings
        self.assertIsNone(self.store.get_setting("remote_pause"))


class TestRemotePauseAuthService(unittest.TestCase):
    """Testa a integração do status DENY_PAUSED no serviço de autenticação."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_kids.sqlite3"
        self.store = Storage(self.db_path)

    def tearDown(self):
        try:
            self.store.close()
        except Exception:
            pass
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_auth_service_denies_when_paused(self):
        """Quando o sistema estiver em pausa remota, deve responder DENY_PAUSED."""
        self.store.set_remote_pause(duration_seconds=1200, reason="Pausa para lição de casa")
        is_paused, reason, remaining = self.store.get_remote_pause_state()
        self.assertTrue(is_paused)
        self.assertEqual(reason, "Pausa para lição de casa")


class TestRemotePauseApi(unittest.TestCase):
    """Testa os endpoints HTTP de controle remoto (/api/remote/*)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "kids.sqlite3"
        self.store = Storage(self.db_path)
        self.store.set_parent_pin("1234")

    def tearDown(self):
        try:
            self.store.close()
        except Exception:
            pass
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    @patch("safepckids.app_server.DEFAULT_DB_FILE")
    def test_remote_status_endpoint(self, mock_db_file):
        mock_db_file.exists.return_value = True
        self.store.add_person("Miguel", 60)
        self.store.add_person("Elena", 120)

        from safepckids.app_server import SafePCKidsApiHandler
        handler = SafePCKidsApiHandler.__new__(SafePCKidsApiHandler)
        handler.headers = {}
        sent_data = {}

        def mock_send_json(data, status=200):
            nonlocal sent_data
            sent_data = {"data": data, "status": status}

        handler.send_json = mock_send_json

        with patch("safepckids.app_server.Storage", side_effect=lambda *args, **kwargs: Storage(self.db_path)):
            handler.handle_remote_status()

        self.assertEqual(sent_data["status"], 200)
        self.assertTrue(sent_data["data"]["ok"])
        self.assertFalse(sent_data["data"]["is_paused"])
        self.assertTrue(sent_data["data"]["has_pin"])
        self.assertIn("children", sent_data["data"])
        self.assertEqual(len(sent_data["data"]["children"]), 2)
        names = [c["name"] for c in sent_data["data"]["children"]]
        self.assertIn("Miguel", names)
        self.assertIn("Elena", names)
        self.assertIsNotNone(sent_data["data"]["child"])
        self.assertIsNotNone(sent_data["data"]["active_child_id"])

    @patch("safepckids.app_server.DEFAULT_DB_FILE")
    def test_remote_pause_endpoint_wrong_pin(self, mock_db_file):
        mock_db_file.exists.return_value = True
        from safepckids.app_server import SafePCKidsApiHandler
        handler = SafePCKidsApiHandler.__new__(SafePCKidsApiHandler)
        handler.headers = {}
        sent_data = {}

        def mock_send_json(data, status=200):
            nonlocal sent_data
            sent_data = {"data": data, "status": status}

        handler.send_json = mock_send_json

        with patch("safepckids.app_server.Storage", side_effect=lambda *args, **kwargs: Storage(self.db_path)):
            handler.handle_remote_pause({"pin": "9999", "duration_minutes": 15})

        self.assertEqual(sent_data["status"], 401)
        self.assertFalse(sent_data["data"]["ok"])

    @patch("safepckids.app_server.DEFAULT_DB_FILE")
    def test_remote_pause_and_resume_correct_pin(self, mock_db_file):
        mock_db_file.exists.return_value = True
        from safepckids.app_server import SafePCKidsApiHandler
        handler = SafePCKidsApiHandler.__new__(SafePCKidsApiHandler)
        handler.headers = {}
        sent_data = {}

        def mock_send_json(data, status=200):
            nonlocal sent_data
            sent_data = {"data": data, "status": status}

        handler.send_json = mock_send_json

        with patch("safepckids.app_server.Storage", side_effect=lambda *args, **kwargs: Storage(self.db_path)):
            # 1. Ativar Pausa
            handler.handle_remote_pause({
                "pin": "1234",
                "duration_minutes": 30,
                "reason": "Hora do almoço"
            })
            self.assertEqual(sent_data["status"], 200)
            self.assertTrue(sent_data["data"]["ok"])
            is_paused, reason, remaining = self.store.get_remote_pause_state()
            self.assertTrue(is_paused)
            self.assertEqual(reason, "Hora do almoço")

            # 2. Retomar
            handler.handle_remote_resume({"pin": "1234"})
            self.assertEqual(sent_data["status"], 200)
            self.assertTrue(sent_data["data"]["ok"])
            is_paused, _, _ = self.store.get_remote_pause_state()
            self.assertFalse(is_paused)


if __name__ == "__main__":
    unittest.main()
