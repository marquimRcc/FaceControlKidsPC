"""VM one-liner supports winget-free Python installation from pinned official source."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "Iniciar-FaceKids-VM-Developer.ps1"


class VmPythonBootstrapTests(unittest.TestCase):
    def test_python_org_installer_is_pinned_and_workspace_local(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn(
            "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe", text)
        self.assertIn(
            "5ee42c4eee1e6b4464bb23722f90b45303f79442df63083f05322f1785f5fdde", text)
        self.assertIn("Get-FileHash", text)
        self.assertIn("Include_tcltk=1", text)
        self.assertIn("Include_pip=1", text)
        self.assertIn("InstallAllUsers=0", text)
        self.assertIn("PrependPath=0", text)
        self.assertIn("FaceKids-VM-Lab", text)
        self.assertIn("'runtime\\python311'", text)
        self.assertNotIn("winget.exe install", text)
        self.assertNotIn("regsvr32.exe", text)
        self.assertNotIn("Register-ScheduledTask", text)
        self.assertNotIn("New-Service", text)

    def test_legacy_powershell_51_never_calls_method_on_nullable_os_architecture(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertNotIn("RuntimeInformation]::OSArchitecture.ToString()", text)
        self.assertNotIn(".Hash.ToLowerInvariant()", text)
        self.assertIn("Get-CimInstance Win32_Processor", text)
        self.assertIn("[Environment]::Is64BitOperatingSystem", text)

    def test_p6_finds_same_workspace_venv_before_global_python(self):
        preflight = (ROOT / "scripts" / "Testar-P5-P6-VM-FaceKids.ps1").read_text(
            encoding="utf-8")
        self.assertIn("$labVenv = Join-Path (Split-Path $root -Parent)", preflight)
        self.assertIn("if (Test-Path -LiteralPath $labVenv -PathType Leaf)", preflight)


if __name__ == "__main__":
    unittest.main()
