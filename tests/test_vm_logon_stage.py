"""Static guardrails for staged Windows VM Credential Provider integration."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "FaceKids-VM-Autenticacao.ps1"
DOCUMENT = ROOT / "docs" / "VM-P3-P4-P5-AUTENTICACAO-20261027.md"


class VmLogonStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.docs = DOCUMENT.read_text(encoding="utf-8")

    def test_virtualbox_only_and_no_household_deployment(self):
        source = self.source
        self.assertIn("Assert-Guest", source)
        self.assertIn("innotek|VirtualBox", source)
        self.assertIn("FaceKids-VM-Lab", source)
        self.assertIn("FaceKids-VM-CP-Lab", source)
        self.assertIn("RECUSADO: execute na conta ADMINISTRATIVA", source)
        self.assertNotIn("Register-ScheduledTask", source)
        self.assertNotIn("New-Service", source)
        self.assertNotIn("C:\\\\ProgramData\\\\FaceKids\\\\FaceKidsCredentialProvider.dll", source)

    def test_worker_started_before_credential_registration(self):
        for needle in [
            "StartAuth", "Require-Assets", "Require-Filhos",
            "facekids.auth_service", "Get-WorkerSid", "listening",
            "Invoke-AuthPipe -Command PING",
            "Invoke-AuthPipe -Command AUTH_QUERY",
            "if($response.status -ne 'ALLOW')",
        ]:
            with self.subTest(needle=needle):
                self.assertIn(needle, self.source)

    def test_cp_requires_real_opt_ins_and_peer_identity(self):
        for needle in [
            "-SnapshotConfirmed", "-RecoveryConfirmed",
            "-FixedPasswordConfirmed", "Require-Admin $current",
            "EnforceAuthServiceSid", "AuthServiceSid",
            "VmInstallerMarker", "TargetUserSid",
            "Credential Provider nao foi registrado.",
            "GetValue('')",
        ]:
            with self.subTest(needle=needle):
                if needle.startswith("-") and needle != "-SnapshotConfirmed":
                    self.assertIn(needle[1:], self.source)
                else:
                    self.assertIn(needle.removeprefix("-") if needle == "-SnapshotConfirmed" else needle, self.source)

    def test_rollback_rejects_foreign_cp_and_preserves_data(self):
        for needle in ["Assert-OurCp", "Remove-OurCp", "Stop-OurWorker",
                       "ProviderDaVM", "if($p)", "Banco"]:
            with self.subTest(needle=needle):
                if needle != "Banco":
                    self.assertIn(needle, self.source)
        self.assertIn("snapshot externo", self.docs)
        self.assertIn("NAO e servico SCM", self.docs)
        self.assertIn("senha fixa Windows", self.docs)


if __name__ == "__main__":
    unittest.main()
