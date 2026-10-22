"""Regression guardrails: diagnostic code must not become a live LogonUI
authenticator or register a Credential Provider accidentally during CI,
and the real Credential Provider must enforce user targeting and verified auto-logon.

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

    def test_real_provider_targets_filhos_and_requires_auth(self):
        provider_src = (ROOT / "native/credential_provider_facekids/FaceKidsProvider.cpp").read_text(
            encoding="utf-8"
        )
        credential_src = (ROOT / "native/credential_provider_facekids/FaceKidsCredential.cpp").read_text(
            encoding="utf-8"
        )
        pipe_src = (ROOT / "native/credential_provider_facekids/FaceKidsPipeClient.h").read_text(
            encoding="utf-8"
        )

        # Provider must resolve Filhos SID and only set m_eligible on exact match
        self.assertIn('LookupAccountNameW(nullptr, L"Filhos"', provider_src)
        self.assertIn("m_eligible = true;", provider_src)

        # GetCredentialCount must return 0 credentials if not eligible (e.g. Admin account)
        self.assertIn("*pdwCount = (m_pCredential && m_eligible) ? 1 : 0;", provider_src)

        # Credential must require m_lastAuth.success before serializing
        self.assertIn("GetSerialization(", credential_src)
        self.assertIn("const bool ok = m_lastAuth.success;", credential_src)
        self.assertIn("if (ok && !user.empty() && !pass.empty())", credential_src)
        self.assertIn("CPGSR_RETURN_CREDENTIAL_FINISHED", credential_src)

        # Pipe client must require ALLOW status and set Filhos account
        self.assertIn('result.user = L"Filhos";', pipe_src)
        self.assertIn('result.password = L"1";', pipe_src)

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
        self.assertIn("FaceKidsCredentialProvider.dll", workflow)
        self.assertIn("build-real-credential-provider", workflow)


if __name__ == "__main__":
    unittest.main()
