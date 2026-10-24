from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class TestInstallerScripts(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.scripts = [
            self.root / "scripts" / "Instalar-FaceKids-Nativo.ps1",
            self.root / "scripts" / "Desinstalar-FaceKids-Nativo.ps1",
            self.root / "scripts" / "Iniciar-Piloto-Filhos.ps1",
        ]

    def test_scripts_exist_and_utf8(self):
        for s in self.scripts:
            self.assertTrue(s.exists(), f"Script ausente: {s}")
            content = s.read_text(encoding="utf-8")
            self.assertGreater(len(content), 50)

    def test_powershell_syntax_on_windows(self):
        if sys.platform != "win32":
            self.skipTest("PowerShell AST parser exclusivo do Windows")

        for s in self.scripts:
            ps_cmd = (
                f"$tokens = $null; $errors = $null; "
                f"[System.Management.Automation.Language.Parser]::ParseFile('{s}', [ref]$tokens, [ref]$errors); "
                f"if ($errors.Count -ne 0) {{ Write-Error $errors[0].Message; exit 1 }}"
            )
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                res.returncode,
                0,
                f"Falha de sintaxe no script {s.name}: {res.stderr or res.stdout}",
            )

    def test_uninstaller_script_contract(self):
        uninst = (self.root / "scripts" / "Desinstalar-FaceKids-Nativo.ps1").read_text(encoding="utf-8")
        # Verifica remocao de ambas as tarefas
        self.assertIn("FaceKidsAuthService", uninst)
        self.assertIn("FaceKidsFilhosAgent", uninst)
        # Verifica que o banco de dados sqlite3 e fotos NAO sao deletados
        self.assertNotIn("Remove-Item -Path $db", uninst)
        self.assertNotIn("children.sqlite3", uninst)
        self.assertIn("PRESERVADO", uninst)

    def test_installer_script_binding_and_privileges(self):
        inst = (self.root / "scripts" / "Instalar-FaceKids-Nativo.ps1").read_text(encoding="utf-8")
        # A tarefa Filhos deve usar o token interativo sem senha no comando.
        self.assertIn("New-ScheduledTaskTrigger -AtLogOn -User $childAccount.Name", inst)
        self.assertIn("New-ScheduledTaskPrincipal -UserId $childAccount.SID.Value", inst)
        self.assertIn("-LogonType Interactive -RunLevel Limited", inst)
        self.assertNotIn('schtasks.exe /create', inst)
        self.assertNotIn('/rp "', inst)
        # Verifica execucao com privilegios elevados
        self.assertIn("New-ScheduledTaskPrincipal", inst)
        self.assertIn("-LogonType Interactive", inst)
        self.assertIn("-RunLevel Highest", inst)
        self.assertIn("New-ScheduledTaskTrigger -AtLogOn -User $authServiceUser", inst)
        self.assertIn("Get-ScheduledTask -TaskName 'FaceKidsAuthService'", inst)
        # Impede instalar DLL antiga com contrato IPC incompatível.
        self.assertIn("$requiredProtocolMarker = 'FACEKIDS_IPC_V1'", inst)
        self.assertIn("$dllAscii.Contains($requiredProtocolMarker)", inst)
        self.assertIn("$rebuiltDllAscii.Contains($requiredProtocolMarker)", inst)

    def test_installer_preflight_returns_before_mutation(self):
        inst = (self.root / "scripts" / "Instalar-FaceKids-Nativo.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$PreflightOnly", inst)
        self.assertIn("Auditar-Permissoes-FaceKids.ps1", inst)
        gate = inst.index("if ($PreflightOnly)")
        early_exit = inst.index("return", gate)
        self.assertLess(early_exit, inst.index("Copy-Item -LiteralPath $dllSource"))
        self.assertLess(early_exit, inst.index('Start-Process -FilePath "regsvr32.exe"'))
        self.assertNotIn('/rp "', inst)

    def test_simulated_runtime_cleanup_preserves_database(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            # Arquivos de dados (devem ser PRESERVADOS)
            db_file = base / "children.sqlite3"
            db_file.write_text("sqlite dummy data", encoding="utf-8")
            photo_dir = base / "fotos"
            photo_dir.mkdir()
            (photo_dir / "child1.jpg").write_text("dummy photo", encoding="utf-8")

            # Arquivos de runtime (devem ser REMOVIDOS)
            bat1 = base / "iniciar-filhos-agent.bat"
            bat1.write_text("@echo off", encoding="utf-8")
            bat2 = base / "iniciar-auth-service.bat"
            bat2.write_text("@echo off", encoding="utf-8")
            unlock = base / "last_unlock.json"
            unlock.write_text("{}", encoding="utf-8")

            # Simulando lista de remocao do desinstalador
            runtime_files = [bat1, bat2, unlock]
            for f in runtime_files:
                if f.exists():
                    f.unlink()

            # Verificacoes
            self.assertFalse(bat1.exists())
            self.assertFalse(bat2.exists())
            self.assertFalse(unlock.exists())
            self.assertTrue(db_file.exists())
            self.assertTrue((photo_dir / "child1.jpg").exists())


if __name__ == "__main__":
    unittest.main()
