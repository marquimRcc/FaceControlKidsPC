"""Verificacoes estaticas de higiene de seguranca na UI e instaladores."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent


class TestUiAndFirewallHygiene(unittest.TestCase):
    def test_api_bridge_has_no_hardcoded_pin_fallback(self):
        js = (ROOT / "safepckids" / "ui_assets" / "api_bridge.js").read_text(encoding="utf-8")
        self.assertNotIn('pin === "1234"', js)
        self.assertNotIn("pin === '1234'", js)

    def test_remote_html_escapes_child_fields_before_innerhtml(self):
        html = (ROOT / "safepckids" / "ui_assets" / "remote.html").read_text(encoding="utf-8")
        self.assertIn("function escapeHtml(", html)
        self.assertIn("escapeHtml(c.name", html)

    def test_firewall_rule_8765_is_restricted_to_private_profile(self):
        installer_py = (ROOT / "safepckids" / "installer_engine.py").read_text(encoding="utf-8")
        installer_ps1 = (ROOT / "scripts" / "Instalar-SafePCKids-Nativo.ps1").read_text(encoding="utf-8")
        for content, label in (
            (installer_py, "installer_engine.py"),
            (installer_ps1, "Instalar-SafePCKids-Nativo.ps1"),
        ):
            self.assertIn("SafePCKids_Remote_Control_HTTP", content, label)
            self.assertIn("-LocalPort 8765 -Profile Private", content, label)
            self.assertNotIn("-LocalPort 8765 -Profile Any", content, label)


if __name__ == "__main__":
    unittest.main()
