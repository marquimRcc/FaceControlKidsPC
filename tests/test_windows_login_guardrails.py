"""Regression guardrails: diagnostic code must not become a live LogonUI
authenticator or register a Credential Provider accidentally during CI.

These checks are intentionally scoped to the experimental Windows branch.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NativeLoginGuardrails(unittest.TestCase):
    def test_provider_does_not_generate_windows_credentials(self):
        source = (ROOT / "native/credential_provider_poc/provider.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("GetSerialization(", source)
        body = source.split("GetSerialization(", 1)[1].split(
            "ReportResult(", 1
        )[0]
        self.assertIn("CPGSR_NO_CREDENTIAL_NOT_FINISHED", body)
        self.assertIn("*serial={};", body)
        self.assertNotIn("CPGSR_RETURN_CREDENTIAL_FINISHED", body)
        self.assertNotIn("CPGSR_RETURN_NO_CREDENTIAL_FINISHED", body)

    def test_workflows_never_register_credential_provider(self):
        workflow_folder = ROOT / ".github/workflows"
        workflows = sorted(workflow_folder.glob("*.yml"))
        self.assertTrue(workflows)
        forbidden = (
            "regsvr32",
            "register-credentialprovider",
            "authentication\\credential providers",
            "authentication/credential providers",
        )
        for filename in workflows:
            content = filename.read_text(encoding="utf-8").lower()
            with self.subTest(workflow=filename.name):
                for token in forbidden:
                    self.assertNotIn(token, content)

    def test_host_only_diagnostic_build_is_separate(self):
        workflow = (ROOT / ".github/workflows/credential-provider-build.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("FACEKIDS_DIAGNOSTIC_HOST_TEST", workflow)
        self.assertIn("FaceKidsDiagnosticHostTest.dll", workflow)
        self.assertIn("FaceKidsDiagnosticProvider.dll", workflow)
        self.assertIn("FaceKidsProviderHost.exe", workflow)


if __name__ == "__main__":
    unittest.main()
