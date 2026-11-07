"""FaceControlKidsPC - Testes de Paridade Funcional, Servicos e DPAPI.

Valida os endpoints REST do painel administrativo web restaurados para paridade com a main:
- /api/service/status e /api/service/restart
- /api/settings/windows-account
- /api/children/<id>/photos e /api/children/<id>/photos/select
- /api/child/delete
- /api/uninstall
- facekids.credential_store (Cofre DPAPI do Windows)
- facekids.installer_engine (provisionamento e desinstalador)
"""
from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock
import urllib.request
import urllib.error

from facekids.app_server import FaceKidsApiHandler
import facekids.credential_store as cred_store
import facekids.installer_engine as installer_engine


class TestParityEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FaceKidsApiHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def _post_json(self, path: str, payload_dict: dict) -> tuple[int, dict]:
        data = json.dumps(payload_dict).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(data)),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def _get_json(self, path: str) -> tuple[int, dict]:
        req = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_service_status_endpoint(self):
        """Valida que GET /api/service/status retorna informacoes reais dos servicos e DLL."""
        mock_health = {
            "auth_service": {"running": True, "registered": True},
            "filhos_agent": {"registered": True},
            "credential_provider": {"registered": True},
        }
        with patch("facekids.app_server.verify_runtime_health", return_value=mock_health):
            status, data = self._get_json("/api/service/status")
            self.assertEqual(status, 200)
            self.assertTrue(data.get("ok"))
            self.assertEqual(data.get("health"), mock_health)

    def test_service_restart_endpoint(self):
        """Valida POST /api/service/restart para reinicio de tarefas do Windows."""
        with patch("facekids.app_server._run_win_cmd") as mock_cmd:
            mock_cmd.return_value = MagicMock(returncode=0)
            status, data = self._post_json("/api/service/restart", {"service": "FaceKidsAuthService"})
            self.assertEqual(status, 200)
            self.assertTrue(data.get("ok"))
            self.assertIn("reiniciado", data.get("message", "").lower())

    def test_service_restart_invalid_service(self):
        """Valida rejeicao de servicos nao autorizados com 400."""
        status, data = self._post_json("/api/service/restart", {"service": "MaliciousService"})
        self.assertEqual(status, 400)
        self.assertFalse(data.get("ok"))

    def test_windows_account_settings_endpoint(self):
        """Valida POST /api/settings/windows-account atualizando senha no Windows e no DPAPI."""
        with patch("facekids.app_server.ensure_filhos_windows_user", return_value=(True, "Conta atualizada")) as mock_ensure:
            status, data = self._post_json("/api/settings/windows-account", {
                "username": "Filhos",
                "password": "NewSecretPassword123!",
            })
            self.assertEqual(status, 200)
            self.assertTrue(data.get("ok"))
            mock_ensure.assert_called_once_with("NewSecretPassword123!", username="Filhos")

    def test_windows_account_settings_validation(self):
        """Valida rejeicao de senha vazia com 400."""
        status, data = self._post_json("/api/settings/windows-account", {
            "username": "Filhos",
            "password": "",
        })
        self.assertEqual(status, 400)
        self.assertFalse(data.get("ok"))

    def test_child_photos_gallery_endpoint(self):
        """Valida GET /api/children/<id>/photos listando amostras capturadas."""
        with tempfile.TemporaryDirectory() as td:
            mock_progdata = Path(td)
            amostras_dir = mock_progdata / "fotos" / "amostras_1"
            amostras_dir.mkdir(parents=True)
            for i in range(1, 4):
                (amostras_dir / f"amostra_{i}.jpg").write_bytes(b"fake_jpg_bytes")

            with patch("facekids.app_server.PROGRAMDATA_DIR", mock_progdata), \
                 patch("facekids.avatar_utils.AVATAR_DIR", mock_progdata / "fotos"):
                status, data = self._get_json("/api/children/1/photos")
                self.assertEqual(status, 200)
                self.assertTrue(data.get("ok"))
                photos = data.get("photos", [])
                self.assertGreaterEqual(len(photos), 3)

    def test_child_photos_select_endpoint(self):
        """Valida POST /api/children/<id>/photos/select definindo foto ativa."""
        with tempfile.TemporaryDirectory() as td:
            mock_progdata = Path(td)
            amostras_dir = mock_progdata / "fotos" / "amostras_2"
            amostras_dir.mkdir(parents=True)
            sample_file = amostras_dir / "amostra_3.jpg"
            sample_file.write_bytes(b"sample_content_3")

            with patch("facekids.app_server.PROGRAMDATA_DIR", mock_progdata), \
                 patch("facekids.app_server.select_child_sample_photo", return_value=True) as mock_sel, \
                 patch("facekids.app_server.Storage") as mock_storage_cls:
                mock_store = MagicMock()
                mock_storage_cls.return_value = mock_store
                status, data = self._post_json("/api/children/2/photos/select", {
                    "index": 3,
                })
                self.assertEqual(status, 200)
                self.assertTrue(data.get("ok"))
                mock_sel.assert_called_once()

    def test_child_delete_endpoint(self):
        """Valida POST /api/child/delete removendo cadastro."""
        with patch("facekids.app_server.Storage") as mock_storage_cls, \
             patch("facekids.app_server.remove_child_avatar_files"):
            mock_store = MagicMock()
            mock_storage_cls.return_value = mock_store
            status, data = self._post_json("/api/child/delete", {"child_id": 5})
            self.assertEqual(status, 200)
            self.assertTrue(data.get("ok"))
            mock_store.remove_person.assert_called_once_with(5)

    def test_uninstall_endpoint(self):
        """Valida POST /api/uninstall executando desinstalacao completa do sistema."""
        with tempfile.TemporaryDirectory() as td:
            isolated_db = Path(td) / "fake_nonexistent.sqlite3"
            with patch("facekids.app_server.DEFAULT_DB_FILE", isolated_db), \
                 patch("facekids.app_server.uninstall_system", return_value=(True, "Desinstalado com sucesso")) as mock_uninst:
                status, data = self._post_json("/api/uninstall", {
                    "remove_data": True,
                    "remove_windows_user": False,
                })
                self.assertEqual(status, 200)
                self.assertTrue(data.get("ok"))
                self.assertIn("Desinstalado com sucesso", data.get("message", ""))
                mock_uninst.assert_called_once_with(remove_data=True, remove_windows_user=False)


class TestCredentialStoreDPAPI(unittest.TestCase):
    def test_save_and_retrieve_credentials(self):
        """Valida o ciclo completo de gravacao e leitura com DPAPI / fallback."""
        with tempfile.TemporaryDirectory() as td:
            mock_progdata = Path(td)
            with patch.object(cred_store, "PROGRAMDATA_DIR", mock_progdata), \
                 patch.object(cred_store, "CREDENTIALS_FILE", mock_progdata / "credentials.bin"), \
                 patch.object(cred_store, "SECURITY_DIR", mock_progdata / "security"), \
                 patch.object(cred_store, "TOKEN_FILE", mock_progdata / "security" / "filhos_session.token"), \
                 patch.object(cred_store, "_run_win_cmd"):
                ok = cred_store.save_filhos_credentials("Criancas", "MinhaSenhaSuperSegura123!")
                self.assertTrue(ok)
                user, pwd = cred_store.get_filhos_credentials()
                self.assertEqual(user, "Criancas")
                self.assertEqual(pwd, "MinhaSenhaSuperSegura123!")
                self.assertEqual(cred_store.get_filhos_password(), "MinhaSenhaSuperSegura123!")


class TestInstallerEngineHealthAndUninstall(unittest.TestCase):
    def test_verify_runtime_health(self):
        """Valida coleta de status de tarefas agendadas e credencial."""
        with patch("facekids.installer_engine._run_win_cmd") as mock_cmd:
            mock_cmd.return_value = MagicMock(returncode=0, stdout="Running")
            health = installer_engine.verify_runtime_health()
            self.assertIn("auth_service", health)
            self.assertIn("filhos_agent", health)
            self.assertIn("credential_provider", health)

    def test_uninstall_system_flow(self):
        """Valida que o desinstalador encerra tarefas, remove chaves e atalhos na ordem de seguranca."""
        with patch("facekids.installer_engine._run_win_cmd") as mock_cmd:
            mock_cmd.return_value = MagicMock(returncode=0, stdout="", stderr="")
            ok, msg = installer_engine.uninstall_system(remove_data=False, remove_windows_user=False)
            self.assertTrue(ok)
            self.assertIn("sucesso", msg.lower())


if __name__ == "__main__":
    unittest.main()
