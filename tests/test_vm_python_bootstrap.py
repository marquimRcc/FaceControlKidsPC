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


if __name__ == "__main__":
    unittest.main()
