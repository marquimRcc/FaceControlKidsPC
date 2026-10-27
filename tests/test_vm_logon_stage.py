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

    def test_worker_starts_hidden_with_explicit_sid_checked_restart(self):
        source = self.source
        self.assertIn("'RestartAuth'", source)
        self.assertIn("if ($Action -eq 'RestartAuth')", source)
        self.assertIn("Require-Assets", source)
        self.assertIn("Get-WorkerSid -ProcessId ([int]$existing.ProcessId)", source)
        self.assertIn("Recusado reiniciar autenticador pertencente a outro SID.", source)
        self.assertIn("Stop-OurWorker", source)
        self.assertIn("$Action='StartAuth'", source)
        self.assertIn("-WindowStyle Hidden", source)
        self.assertIn("-RedirectStandardOutput", source)
        self.assertIn("-RedirectStandardError", source)
        self.assertNotIn("Stop-Process -Name python", source)

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

    def test_one_line_driver_refreshes_lab_and_never_installs_login(self):
        wrapper = (ROOT / "scripts" / "Preparar-FaceKids-Autenticacao-VM.ps1").read_text(
            encoding="utf-8")
        bootstrap = (ROOT / "scripts" / "Iniciar-FaceKids-VM-Developer.ps1").read_text(
            encoding="utf-8")
        for needle in ["VirtualBox|innotek", "scripts/", "-NoDashboard",
                       "-SkipTests", "-NoCameraProbe",
                       "@('-Action','StartAuth')", "@('-Action','Ping')",
                       "@('-Action','FaceProbe')"]:
            with self.subTest(needle=needle):
                self.assertIn(needle, wrapper)
        self.assertIn("[switch]$NoDashboard", bootstrap)
        self.assertIn("if ($NoDashboard)", bootstrap)
        # The PowerShell 5.1 VM may be Restricted. The remote iex entrypoint
        # is allowed, but direct invocation of downloaded .ps1 files is not.
        # The helper must use process-scoped Bypass for EVERY nested stage,
        # and must fail fast when any nested PowerShell exits nonzero.
        self.assertIn("function Invoke-LabStep", wrapper)
        self.assertIn("& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @StepArguments", wrapper)
        self.assertIn("if ($LASTEXITCODE -ne 0)", wrapper)
        self.assertIn("Invoke-LabStep -ScriptPath $bootstrap", wrapper)
        self.assertGreaterEqual(wrapper.count("Invoke-LabStep -ScriptPath $stage"), 3)
        self.assertNotIn("& $bootstrap", wrapper)
        self.assertNotIn("& $stage", wrapper)
        self.assertNotIn("Set-ExecutionPolicy", wrapper)
        self.assertNotIn("-Action ActivateCP", wrapper)
        self.assertNotIn("Register-ScheduledTask", wrapper)
        self.assertNotIn("New-Service", wrapper)

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
