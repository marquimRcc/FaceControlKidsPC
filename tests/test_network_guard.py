"""Testes unitarios para o modulo de protecao de rede SafePCKids (AdGuard Family + Firewall)."""
import unittest
from unittest.mock import patch, MagicMock

from safepckids.network_guard import (
    ADGUARD_IPV4_PRIMARY,
    ADGUARD_IPV4_SECONDARY,
    ADGUARD_DOH_TEMPLATE,
    get_protection_status,
    _run_powershell,
    is_admin,
    _run_powershell_elevated,
)


class TestNetworkGuard(unittest.TestCase):
    def test_adguard_constants(self):
        self.assertEqual(ADGUARD_IPV4_PRIMARY, "94.140.14.15")
        self.assertEqual(ADGUARD_IPV4_SECONDARY, "94.140.15.16")
        self.assertIn("https://dns-family.adguard.com/dns-query", ADGUARD_DOH_TEMPLATE)

    def test_get_protection_status_structure(self):
        status = get_protection_status()
        self.assertIsInstance(status, dict)
        self.assertIn("active", status)
        self.assertIn("dns_configured", status)
        self.assertIn("firewall_rules_present", status)
        self.assertIn("adguard_ipv4", status)
        self.assertIn("doh_template", status)
        self.assertIn("details", status)

    @patch("safepckids.network_guard.subprocess.run")
    def test_run_powershell_success(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "OK\n"
        mock_res.stderr = ""
        mock_run.return_value = mock_res

        ok, out = _run_powershell("Write-Output 'OK'")
        self.assertTrue(ok)
        self.assertEqual(out, "OK")

    @patch("safepckids.network_guard.subprocess.run")
    def test_run_powershell_failure(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stdout = ""
        mock_res.stderr = "Command failed"
        mock_run.return_value = mock_res

        ok, out = _run_powershell("invalid")
        self.assertFalse(ok)
        self.assertEqual(out, "Command failed")

    def test_is_admin_returns_bool(self):
        val = is_admin()
        self.assertIsInstance(val, bool)

    @patch("safepckids.network_guard.is_admin", return_value=True)
    @patch("safepckids.network_guard._run_powershell")
    def test_run_powershell_elevated_admin(self, mock_run_ps, mock_admin):
        mock_run_ps.return_value = (True, "OK")
        ok, out = _run_powershell_elevated("test")
        self.assertTrue(ok)
        self.assertEqual(out, "OK")


if __name__ == "__main__":
    unittest.main()
