import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class LinuxInstallerTests(unittest.TestCase):
    def test_unit_runs_protected_and_limits_device_access(self):
        unit = (ROOT / "packaging/facekids-linux.service").read_text(encoding="utf-8")
        self.assertIn("User=root", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("ReadWritePaths=/var/lib/facekids", unit)
        self.assertIn("DevicePolicy=closed", unit)
        self.assertIn("DeviceAllow=/dev/video0 rw", unit)
        self.assertIn("UMask=0077", unit)
        self.assertIn("RuntimeDirectoryMode=0700", unit)
        self.assertIn("CapabilityBoundingSet=", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", unit)
        self.assertIn("IPAddressDeny=any", unit)

    def test_installer_does_not_start_before_enrollment(self):
        script = (ROOT / "scripts/Instalar-FaceKids-RegataOS.sh").read_text(encoding="utf-8")
        commands = [line.strip() for line in script.splitlines() if line.strip() and not line.lstrip().startswith("#") and not line.lstrip().startswith("echo ")]
        self.assertNotIn("systemctl enable facekids-linux.service", script)
        self.assertFalse(any("systemctl start facekids-linux" in line for line in commands))
        self.assertFalse(any("systemctl enable --now" in line for line in commands))
        self.assertIn(
            'echo "Repita para cada número configurado; depois: sudo systemctl enable --now facekids-linux"',
            script,
        )
        self.assertIn('setup --children "${CHILD_COUNT}"', script)
        runtime = (ROOT / "facekids/linux_runtime.py").read_text(encoding="utf-8")
        self.assertIn("enrollments_complete(self.references, self.engine.people)", runtime)
        self.assertIn("chmod 0600 /var/lib/facekids/criancas.sqlite3", script)

    def test_uninstaller_preserves_database(self):
        script = (ROOT / "scripts/Desinstalar-FaceKids-RegataOS.sh").read_text(encoding="utf-8")
        commands = [line.strip() for line in script.splitlines() if line.strip().startswith("rm ")]
        self.assertTrue(any("/usr/lib/facekids" in line for line in commands))
        self.assertFalse(any("/var/lib/facekids" in line for line in commands))

    def test_pam_is_opt_in_and_has_recovery_script(self):
        installer = (ROOT / "scripts/Instalar-FaceKids-RegataOS.sh").read_text(encoding="utf-8")
        enable = (ROOT / "scripts/Ativar-PAM-FaceKids-RegataOS.sh").read_text(encoding="utf-8")
        disable = (ROOT / "scripts/Desativar-PAM-FaceKids-RegataOS.sh").read_text(encoding="utf-8")
        self.assertNotIn('bash "${SOURCE_DIR}/scripts/Ativar-PAM-FaceKids-RegataOS.sh"', installer)
        self.assertIn("/usr/local/sbin/facekids-enable-pam", installer)
        self.assertIn("/usr/local/sbin/facekids-disable-pam", installer)
        self.assertIn("pam_exec.so quiet /usr/local/libexec/facekids-pam-helper", enable)
        self.assertIn("kde sddm", enable)
        self.assertIn("pam-backup", enable)
        self.assertIn("pam-backup", disable)
        self.assertIn("facekids-pam-helper", disable)
        self.assertIn("STAGED_FILES", enable)
        self.assertIn("Só altera PAM depois", enable)

    def test_child_account_script_removes_privileged_groups(self):
        script = (ROOT / "scripts/Criar-Conta-Filhos-RegataOS.sh").read_text(encoding="utf-8")
        self.assertIn('usermod --groups "" "${CHILD_USER}"', script)
        self.assertIn('id -G "${CHILD_USER}"', script)
        self.assertNotIn("--groups video", script)
        self.assertNotIn("--append --groups video", script)

    def test_uninstaller_restores_pam_before_removing_helper(self):
        script = (ROOT / "scripts/Desinstalar-FaceKids-RegataOS.sh").read_text(
            encoding="utf-8"
        )
        restore = script.index("facekids-disable-pam")
        remove_helper = script.index("rm -f /usr/local/libexec/facekids-pam-helper")
        self.assertLess(restore, remove_helper)

    def test_linux_ci_checks_scripts_and_integration_modules(self):
        workflow = (ROOT / ".github/workflows/linux-regataos.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("python-version: \"3.13\"", workflow)
        self.assertIn("tests.test_linux_runtime", workflow)
        self.assertIn("scripts/*RegataOS.sh", workflow)
        self.assertIn('bash -n "$script"', workflow)
        self.assertIn('systemd-analyze verify "$unit"', workflow)


if __name__ == "__main__":
    unittest.main()
