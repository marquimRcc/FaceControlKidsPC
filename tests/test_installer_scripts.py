from pathlib import Path
import subprocess
import sys
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


if __name__ == "__main__":
    unittest.main()
