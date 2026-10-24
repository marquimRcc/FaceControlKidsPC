#define WIN32_LEAN_AND_MEAN
#include "FaceKidsPipePeerIdentity.h"
#include <iostream>
#include <string>

int main() {
    std::wstring ignored;
    if (FaceKidsPipePeerIdentity::QueryServerUserSid(INVALID_HANDLE_VALUE, ignored) ||
        FaceKidsPipePeerIdentity::MatchesExpectedSid(INVALID_HANDLE_VALUE, L"S-1-5-18") ||
        FaceKidsPipePeerIdentity::MatchesExpectedSid(nullptr, L"") ||
        FaceKidsPipePeerIdentity::MatchesExpectedSid(nullptr, L"not-a-sid")) {
        std::wcerr << L"FAIL: invalid pipe or expected SID accepted\n";
        return 1;
    }

    // Isolated synthetic pipe, created in THIS test process: no FaceKids pipe,
    // LogonUI, Credential Provider registration, or real credentials touched.
    std::wstring pipeName = L"\\\\.\\pipe\\FaceKidsPeerSidSynthetic-" +
                            std::to_wstring(GetCurrentProcessId());
    HANDLE server = CreateNamedPipeW(
        pipeName.c_str(), PIPE_ACCESS_DUPLEX,
        PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
        1, 512, 512, 1000, nullptr);
    if (server == INVALID_HANDLE_VALUE) return 2;

    HANDLE client = CreateFileW(pipeName.c_str(), GENERIC_READ | GENERIC_WRITE,
                                0, nullptr, OPEN_EXISTING, 0, nullptr);
    if (client == INVALID_HANDLE_VALUE) {
        CloseHandle(server);
        return 3;
    }
    BOOL connected = ConnectNamedPipe(server, nullptr);
    if (!connected && GetLastError() != ERROR_PIPE_CONNECTED) {
        CloseHandle(client);
        CloseHandle(server);
        return 4;
    }

    DWORD observedPid = 0;
    const bool queried = FaceKidsPipePeerIdentity::QueryServerUserSid(
        client, ignored, &observedPid);
    if (!queried || ignored.empty() || observedPid != GetCurrentProcessId()) {
        CloseHandle(client);
        CloseHandle(server);
        std::wcerr << L"FAIL: synthetic server identity lookup\n";
        return 5;
    }
    if (!FaceKidsPipePeerIdentity::MatchesExpectedSid(client, ignored) ||
        FaceKidsPipePeerIdentity::MatchesExpectedSid(client, L"S-1-0-0") ||
        FaceKidsPipePeerIdentity::MatchesExpectedSid(client, L"bad-sid")) {
        CloseHandle(client);
        CloseHandle(server);
        std::wcerr << L"FAIL: SID comparison accepted impostor or denied real owner\n";
        return 6;
    }
    CloseHandle(client);
    DisconnectNamedPipe(server);
    CloseHandle(server);
    std::wcout << L"PASS: synthetic pipe token owner lookup and negative SID checks\n";
    return 0;
}
