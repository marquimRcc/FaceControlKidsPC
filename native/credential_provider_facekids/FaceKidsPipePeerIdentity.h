#pragma once
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <sddl.h>
#include <string>
#include <vector>

// Diagnostic helper only. A token user SID comparison is not cryptographic
// attestation of the executable, and cannot defend against code running
// as the trusted account. Do not enable enforcement in LogonUI without
// controlled VM tests and a verified expected SID source (protected HKLM).
class FaceKidsPipePeerIdentity final {
public:
    static bool QueryServerUserSid(HANDLE pipe, std::wstring& outSid, DWORD* outPid = nullptr) {
        outSid.clear();
        if (outPid) *outPid = 0;
        if (!pipe || pipe == INVALID_HANDLE_VALUE) return false;

        ULONG pid = 0;
        if (!GetNamedPipeServerProcessId(pipe, &pid) || pid == 0) return false;
        HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
        if (!process) return false;

        HANDLE token = nullptr;
        const BOOL opened = OpenProcessToken(process, TOKEN_QUERY, &token);
        CloseHandle(process);
        if (!opened || !token) return false;

        DWORD required = 0;
        GetTokenInformation(token, TokenUser, nullptr, 0, &required);
        if (required < sizeof(TOKEN_USER) || required > 65536) {
            CloseHandle(token);
            return false;
        }
        std::vector<BYTE> tokenBytes(required);
        const BOOL queried = GetTokenInformation(
            token, TokenUser, tokenBytes.data(), required, &required);
        CloseHandle(token);
        if (!queried || required < sizeof(TOKEN_USER)) return false;

        const auto* user = reinterpret_cast<const TOKEN_USER*>(tokenBytes.data());
        if (!IsValidSid(user->User.Sid)) return false;
        LPWSTR printable = nullptr;
        if (!ConvertSidToStringSidW(user->User.Sid, &printable) || !printable) return false;
        outSid.assign(printable);
        LocalFree(printable);
        if (outPid) *outPid = static_cast<DWORD>(pid);
        return true;
    }

    // A pure decision point for isolated synthetic SID and policy tests.
    static bool EvaluatePolicy(HANDLE pipe, DWORD enabled,
                               const std::wstring& expectedSid) {
        if (enabled == 0) return true;
        if (enabled != 1) return false;
        return MatchesExpectedSid(pipe, expectedSid);
    }

    // Opt-in policy stored under protected HKLM. No value => legacy compatibility.
    // A configured invalid/unreadable policy FAILS CLOSED. Never enable on
    // family hardware before VM confirms the interactive auth-service SID.
    static bool AuthorizeIfConfigured(HANDLE pipe) {
        static const wchar_t* key =
            L"SOFTWARE\\FaceControlKidsPC\\CredentialProvider";
        DWORD enabled = 0;
        DWORD size = sizeof(enabled);
        LSTATUS result = RegGetValueW(
            HKEY_LOCAL_MACHINE, key, L"EnforceAuthServiceSid",
            RRF_RT_REG_DWORD, nullptr, &enabled, &size);
        if (result == ERROR_FILE_NOT_FOUND || result == ERROR_PATH_NOT_FOUND)
            return true;
        if (result != ERROR_SUCCESS || size != sizeof(enabled))
            return false;
        if (enabled == 0) return true;
        if (enabled != 1) return false;

        wchar_t expected[256] = {};
        DWORD stringBytes = sizeof(expected);
        result = RegGetValueW(
            HKEY_LOCAL_MACHINE, key, L"AuthServiceSid",
            RRF_RT_REG_SZ, nullptr, expected, &stringBytes);
        if (result != ERROR_SUCCESS || expected[0] == L'\0')
            return false;
        return EvaluatePolicy(pipe, enabled, expected);
    }

    static bool MatchesExpectedSid(HANDLE pipe, const std::wstring& expectedSid) {
        if (expectedSid.empty()) return false;
        PSID parsed = nullptr;
        if (!ConvertStringSidToSidW(expectedSid.c_str(), &parsed) || !parsed) return false;
        std::wstring observed;
        const bool observedOk = QueryServerUserSid(pipe, observed);
        PSID actual = nullptr;
        const bool actualOk = observedOk &&
            ConvertStringSidToSidW(observed.c_str(), &actual) && actual;
        const bool matches = actualOk && EqualSid(parsed, actual);
        if (actual) LocalFree(actual);
        LocalFree(parsed);
        return matches;
    }
};
