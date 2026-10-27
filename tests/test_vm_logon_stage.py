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

    def test_launcher_pid_can_differ_from_real_named_pipe_server_pid(self):
        source = self.source
        preflight = (ROOT / "scripts" / "Validar-Passo2-FaceKids-VM.ps1").read_text(
            encoding="utf-8")
        # The Windows virtualenv Python redirector can change the process PID.
        # Resolve the real server from its own status and verify its SID and CLI.
        for token in [
            "$actualPid=[int]$s.pid",
            "launcherPid=$p.Id",
            "processId=$actualPid",
            "Get-WorkerSid -ProcessId $actualPid",
            "$actual.CommandLine -notmatch 'facekids[.]auth_service'",
            "$p.CommandLine -notlike ('*'+$statusFile+'*')",
            "[int]$serverState.pid -ne [int]$p.ProcessId",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, source)
        self.assertNotIn("$actualPid=[int]$status.pid", source)
        self.assertIn("$s=Get-Content -LiteralPath $statusFile -Raw | ConvertFrom-Json", source)
        self.assertIn("if($s.phase -eq 'listening')", source)
        for token in [
            "vm-auth-status.json",
            "WORKER_TRACKED_PID_DIFFERS_FROM_SERVER",
            "$p.CommandLine -notlike ('*'+$serverStatusFile+'*')",
            "[int]$reported.pid -ne $trackedPid",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, preflight)

    def test_existing_live_server_is_adopted_only_with_proven_identity(self):
        source = self.source
        for token in [
            "if($other.Count -gt 0){",
            "if ($other.Count -ne 1)",
            "[int]$state.pid -ne [int]$existing.ProcessId",
            "$existing.CommandLine -notlike ('*'+$statusFile+'*')",
            "Get-WorkerSid -ProcessId ([int]$existing.ProcessId)",
            "$existingSid -ne [string]$current.User.Value",
            "$reply=Invoke-AuthPipe -Command PING",
            "$reply.status -ne 'PONG'",
            "processId=[int]$existing.ProcessId",
            "nenhum PID foi encerrado",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, source)
        self.assertNotIn("Stop-Process -Name python", source)

    def test_cp_requires_real_opt_ins_and_peer_identity(self):
        for needle in [
            "-RecoveryConfirmed",
            "-FixedPasswordConfirmed", "Require-Admin $current",
            "EnforceAuthServiceSid", "AuthServiceSid",
            "VmInstallerMarker", "TargetUserSid",
            "Credential Provider nao foi registrado.",
            "GetValue('')",
        ]:
            with self.subTest(needle=needle):
                self.assertIn(needle.lstrip("-"), self.source)

    def test_step2_preflight_only_reads_live_lab_state(self):
        preflight = (ROOT / "scripts" / "Validar-Passo2-FaceKids-VM.ps1").read_text(
            encoding="utf-8")
        guide = (ROOT / "docs" / "VM-PASSO2-PREFLIGHT-20261027.md").read_text(
            encoding="utf-8")
        for needle in ["VirtualBox|innotek", "Get-LocalUser", "GetOwnerSid",
                       "vm-auth-worker.json", "CredentialProviderNotRegistered",
                       "Preflight tecnico aprovado"]:
            with self.subTest(needle=needle):
                self.assertIn(needle, preflight)
        self.assertNotIn("New-LocalUser", preflight)
        self.assertNotIn("Register-ScheduledTask", preflight)
        self.assertNotIn("regsvr32", preflight)
        self.assertNotIn("exit 2", preflight)
        self.assertIn("-RecoveryConfirmed", guide)
        self.assertIn("-FixedPasswordConfirmed", guide)

    def test_step2_diagnostics_record_success_and_failure_with_reason_codes(self):
        preflight = (ROOT / "scripts" / "Validar-Passo2-FaceKids-VM.ps1").read_text(
            encoding="utf-8")
        for needle in [
            "function Get-WorkerDiagnostics", "function Test-AuthPipePing",
            "function Save-Diagnostic", "WORKER_RECORD_MISSING",
            "WORKER_EXITED_OR_STALE_PID", "WORKER_OWNER_SID_MISMATCH",
            "WORKER_SID_QUERY_FAILED", "WORKER_SID_QUERY_EXCEPTION",
            "IPC_PONG", "PIPE_UNAVAILABLE", "reason_code",
            "facekids-vm-events.jsonl", "passo2-ultimo.json",
            "Add-Content -LiteralPath $historyFile",
            "Set-Content -LiteralPath $lastFile",
            "PRECHECK_BLOQUEADO", "Preflight tecnico aprovado",
            "VALIDACAO MANUAL PENDENTE",
        ]:
            with self.subTest(needle=needle):
                self.assertIn(needle, preflight)
        self.assertNotIn("throw 'Preflight VM: uma ou mais verificacoes tecnicas falharam.'",
                         preflight)
        self.assertNotIn("exit 2", preflight)
        self.assertNotIn("result.password", preflight)
        self.assertNotIn("New-LocalUser", preflight)

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
        self.assertIn("login administrativo", self.docs)
        self.assertNotIn("SnapshotConfirmed", self.source)
        self.assertIn("NAO e servico SCM", self.docs)
        self.assertIn("senha fixa Windows", self.docs)


if __name__ == "__main__":
    unittest.main()
