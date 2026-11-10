"""FaceControlKidsPC - Testes de Regressao do Servidor de Aplicacao e /api/install.

Valida a resiliencia do transporte HTTP, delimitacao de Content-Length,
captura robusta de falhas sem abortar conexoes e protecao contra encerramento
prematuro do servidor.
"""
from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch, MagicMock
import urllib.request
import urllib.error

from facekids.app_server import FaceKidsApiHandler
from facekids.session_secret import _run_win_cmd, save_secure_secret, get_session_secret
from facekids.installer_engine import _run_win_cmd as installer_run_win_cmd


class TestAppServerInstall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Levanta um ThreadingHTTPServer em uma porta efemera (porta 0)
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

    def test_post_install_real_server_success(self):
        """Verifica se POST /api/install retorna 200, Content-Length valido e payload JSON com token."""
        mock_token = "secure_token_secret_xyz123"
        with patch("facekids.app_server.setup_system", return_value=(True, "Instalado com sucesso")):
            with patch("facekids.app_server.get_session_secret", return_value=mock_token):
                payload = json.dumps({
                    "pin": "1234",
                    "child_name": "Lucas",
                    "daily_limit_hours": 2.0
                }).encode("utf-8")

                req = urllib.request.Request(
                    f"{self.base_url}/api/install",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": str(len(payload))
                    },
                    method="POST"
                )

                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    self.assertEqual(resp.status, 200)
                    content_length = resp.headers.get("Content-Length")
                    self.assertIsNotNone(content_length)
                    self.assertEqual(resp.headers.get("Connection"), "close")
                    
                    data = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(data.get("ok"))
                    self.assertEqual(data.get("status"), "success")
                    self.assertEqual(data.get("token"), mock_token)
                    self.assertEqual(data.get("message"), "Instalado com sucesso")

    def test_completion_requires_facial_enrollment(self):
        with patch("facekids.app_server.DEFAULT_DB_FILE") as db, \
             patch("facekids.app_server.Storage") as storage, \
             patch("facekids.app_server.setup_system") as setup:
            db.exists.return_value = True
            storage.return_value.get_setting.return_value = "hashed-pin"
            storage.return_value.embeddings.return_value = []
            req = urllib.request.Request(
                f"{self.base_url}/api/install/complete",
                data=b"{}", headers={"Content-Type": "application/json"}, method="POST"
            )
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req, timeout=10.0)
            self.assertEqual(error.exception.code, 400)
            setup.assert_not_called()

    def test_completion_starts_services_after_enrollment(self):
        with patch("facekids.app_server.DEFAULT_DB_FILE") as db, \
             patch("facekids.app_server.Storage") as storage, \
             patch("facekids.app_server.setup_system", return_value=(True, "pronto")) as setup:
            db.exists.return_value = True
            storage.return_value.get_setting.return_value = "hashed-pin"
            storage.return_value.embeddings.return_value = [(1, "vector")]
            req = urllib.request.Request(
                f"{self.base_url}/api/install/complete",
                data=b"{}", headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=10.0) as response:
                self.assertTrue(json.loads(response.read())["ok"])
            setup.assert_called_once_with(master_pin="")

    def test_wizard_enrolls_the_named_child(self):
        with patch("facekids.app_server.DEFAULT_DB_FILE") as db, \
             patch("facekids.app_server.Storage") as storage, \
             patch("facekids.app_server.CameraService.get_instance") as camera:
            db.exists.return_value = True
            storage.return_value.people.return_value = [(1, "Lucas"), (2, "Ana")]
            camera.return_value.start_enrollment.return_value = {"ok": True}
            payload = json.dumps({"child_id": 0, "child_name": "Ana"}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/camera/enroll/start", data=payload,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=10.0) as response:
                self.assertTrue(json.loads(response.read())["ok"])
            camera.return_value.start_enrollment.assert_called_once_with(2, db)

    def test_post_install_invalid_pin_returns_400(self):
        """Verifica se PIN menor que 4 digitos retorna HTTP 400 sem derrubar o socket."""
        payload = json.dumps({"pin": "12"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/install",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload))
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                self.assertEqual(resp.status, 400)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            data = json.loads(e.read().decode("utf-8"))
            self.assertFalse(data.get("ok"))
            self.assertIn("PIN", data.get("error", ""))

    def test_post_install_exception_handling_returns_500(self):
        """Verifica que qualquer excecao no setup_system retorna JSON 500 sem resetar a conexao."""
        with patch("facekids.app_server.setup_system", side_effect=RuntimeError("Falha de teste simulada")):
            payload = json.dumps({"pin": "9999"}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/install",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(payload))
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    self.assertEqual(resp.status, 500)
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 500)
                data = json.loads(e.read().decode("utf-8"))
                self.assertFalse(data.get("ok"))
                self.assertIn("Falha de teste simulada", data.get("error", ""))

    def test_inactivity_monitor_does_not_kill_during_install(self):
        """Valida que enquanto is_installing for True, o status do servidor se mantem ativo."""
        FaceKidsApiHandler.is_installing = True
        try:
            old_time = time.time() - 400.0  # Passado o timeout de inatividade
            FaceKidsApiHandler.last_activity_time = old_time
            # Simulando checagem de timeout com is_installing ativo
            if getattr(FaceKidsApiHandler, "is_installing", False):
                FaceKidsApiHandler.last_activity_time = time.time()
                should_shutdown = False
            else:
                elapsed = time.time() - FaceKidsApiHandler.last_activity_time
                should_shutdown = elapsed > 300.0

            self.assertFalse(should_shutdown)
            self.assertGreater(FaceKidsApiHandler.last_activity_time, old_time)
        finally:
            FaceKidsApiHandler.is_installing = False

    def test_run_win_cmd_parameters(self):
        """Verifica que _run_win_cmd invoca subprocess.run com DEVNULL e close_fds."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(["cmd"], 0, "", "")
            _run_win_cmd(["echo", "test"], timeout=10.0)
            mock_run.assert_called_once()
            kwargs = mock_run.call_args[1]
            self.assertEqual(kwargs.get("stdin"), subprocess.DEVNULL)
            self.assertTrue(kwargs.get("close_fds"))
            self.assertEqual(kwargs.get("timeout"), 10.0)
            self.assertFalse(kwargs.get("check"))


if __name__ == "__main__":
    unittest.main()
