"""The wizard may report success only after Windows provisioning is verified."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from safepckids import installer_engine as engine


class InstallerCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "source"
        for relative in (
            ".venv/Scripts/python.exe",
            ".venv/Scripts/pythonw.exe",
            "native/credential_provider_safepckids/SafePCKidsCredentialProvider.dll",
            "scripts/Ativar-Desbloqueio-No-Boot.ps1",
            "models/face_detection_yunet_2023mar.onnx",
            "models/face_recognition_sface_2021dec.onnx",
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test")
        data = base / "data"
        patches = (
            patch.object(engine, "PROGRAMDATA_DIR", data),
            patch.object(engine, "SECURITY_DIR", data / "security"),
            patch.object(engine, "CONFIG_FILE", data / "configuracoes.json"),
            patch.object(engine, "DEFAULT_DB_FILE", data / "criancas.sqlite3"),
            patch.object(engine, "INSTALL_MARKER", data / "installation-ready.json"),
            patch.object(engine, "get_production_project_root", return_value=self.root),
            patch.object(engine, "is_admin", return_value=True),
            patch.object(engine, "create_desktop_shortcuts"),
            patch.object(engine, "verify_runtime_health", return_value={
                "auth_service": {"registered": True},
                "filhos_agent": {"registered": True},
                "boot_auth": {"registered": True},
                "credential_provider": {"registered": True},
                "filhos_user": {"exists": True},
            }),
            patch.object(engine.os.path, "exists", return_value=True),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_failed_account_does_not_claim_installation(self):
        with patch.object(engine, "ensure_filhos_windows_user", return_value=(False, "conta falhou")), \
             patch.object(engine, "setup_windows_services") as services:
            ok, message = engine.setup_system("1234", "Ana", filhos_password="1")
        self.assertFalse(ok)
        self.assertIn("conta falhou", message)
        self.assertFalse(engine.INSTALL_MARKER.exists())
        services.assert_not_called()

    def test_existing_filhos_keeps_windows_account_and_saved_password(self):
        with patch.object(engine.ctypes, "windll", create=True) as windows, \
             patch.object(engine, "get_filhos_credentials", return_value=("Filhos", "stored")), \
             patch.object(engine, "_run_win_cmd") as command, \
             patch.object(engine, "save_filhos_credentials") as save:
            windows.netapi32.NetUserGetInfo.return_value = 0
            ok, _ = engine.ensure_filhos_windows_user("1", preserve_existing=True)
        self.assertTrue(ok)
        command.assert_not_called()
        save.assert_not_called()

    def test_failed_task_does_not_claim_installation(self):
        with patch.object(engine, "ensure_filhos_windows_user", return_value=(True, "ok")), \
             patch.object(engine, "setup_windows_services", return_value=(False, "tarefa falhou")):
            ok, message = engine.setup_system("1234", "Ana", filhos_password="1")
        self.assertFalse(ok)
        self.assertIn("tarefa falhou", message)
        self.assertFalse(engine.INSTALL_MARKER.exists())

    def test_success_waits_for_windows_verification(self):
        with patch.object(engine, "ensure_filhos_windows_user", return_value=(True, "ok")), \
             patch.object(engine, "setup_windows_services", return_value=(True, "ok")):
            ok, _ = engine.setup_system("1234", "Ana", filhos_password="1")
        self.assertTrue(ok)
        self.assertTrue(engine.INSTALL_MARKER.is_file())

    def test_first_phase_waits_for_facial_enrollment(self):
        with patch.object(engine, "ensure_filhos_windows_user", return_value=(True, "ok")), \
             patch.object(engine, "setup_windows_services") as services:
            ok, _ = engine.setup_system("1234", "Ana", filhos_password="1", defer_services=True)
        self.assertTrue(ok)
        self.assertFalse(engine.INSTALL_MARKER.exists())
        services.assert_not_called()


if __name__ == "__main__":
    unittest.main()
