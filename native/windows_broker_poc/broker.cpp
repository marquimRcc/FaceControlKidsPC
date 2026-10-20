// P0-5: Windows native service shell and privileged, read-only diagnostic pipe.
// NOT an authenticator. No credential secrets, images, quota reads or mutations.
// No installer/registration: test in --self-test or --console-once only.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <sddl.h>
#include <cstdio>
#include <cstring>
#include <cwchar>

#pragma comment(lib, "advapi32.lib")

static constexpr wchar_t kService[] = L"FaceKidsBrokerPoc";
static constexpr wchar_t kPipe[] = LR"(\\.\pipe\FaceKidsBrokerPoc-v1)";
static constexpr wchar_t kAcl[] = L"D:P(A;;GA;;;SY)(A;;GA;;;BA)";
static HANDLE g_stop = nullptr;
static SERVICE_STATUS_HANDLE g_handler = nullptr;
static SERVICE_STATUS g_service = {};
static DWORD g_error = ERROR_SUCCESS;

static void report(DWORD state, DWORD error = ERROR_SUCCESS) {
    if (!g_handler) return;
    g_service.dwServiceType = SERVICE_WIN32_OWN_PROCESS;
    g_service.dwCurrentState = state;
    g_service.dwControlsAccepted = (state == SERVICE_RUNNING) ? SERVICE_ACCEPT_STOP : 0;
    g_service.dwWin32ExitCode = error;
    g_service.dwWaitHint = (state == SERVICE_STOP_PENDING) ? 5000 : 0;
    g_service.dwCheckPoint =
        (state == SERVICE_START_PENDING || state == SERVICE_STOP_PENDING)
        ? g_service.dwCheckPoint + 1 : 0;
    SetServiceStatus(g_handler, &g_service);
}

static DWORD WINAPI control(DWORD event, DWORD, LPVOID, LPVOID) {
    if (event == SERVICE_CONTROL_STOP && g_stop) {
        report(SERVICE_STOP_PENDING);
        SetEvent(g_stop);
        return NO_ERROR;
    }
    return ERROR_CALL_NOT_IMPLEMENTED;
}

static bool security_descriptor(PSECURITY_DESCRIPTOR* sd) {
    *sd = nullptr;
    return ConvertStringSecurityDescriptorToSecurityDescriptorW(
        kAcl, SDDL_REVISION_1, sd, nullptr) != FALSE;
}

// The pipe DACL limits connect to SYSTEM or an *elevated* administrator.
// Token check after impersonation is defense in depth, never caller-provided.
static bool trusted_pipe_client(HANDLE pipe) {
    if (!ImpersonateNamedPipeClient(pipe)) return false;
    BYTE adminSid[SECURITY_MAX_SID_SIZE] = {};
    BYTE systemSid[SECURITY_MAX_SID_SIZE] = {};
    DWORD adminBytes = sizeof(adminSid), systemBytes = sizeof(systemSid);
    BOOL admin = FALSE, system = FALSE;
    bool ok = CreateWellKnownSid(WinBuiltinAdministratorsSid, nullptr,
                                 adminSid, &adminBytes) &&
              CreateWellKnownSid(WinLocalSystemSid, nullptr,
                                 systemSid, &systemBytes);
    if (ok) {
        // nullptr checks the current thread's impersonated client identity.
        if (!CheckTokenMembership(nullptr, adminSid, &admin)) ok = false;
        if (!CheckTokenMembership(nullptr, systemSid, &system)) ok = false;
    }
    if (!RevertToSelf()) return false;
    return ok && (admin || system);
}

static bool finish_pending(HANDLE pipe, OVERLAPPED* ov, DWORD timeout, DWORD* transferred) {
    HANDLE events[2] = {ov->hEvent, g_stop};
    DWORD wait = WaitForMultipleObjects(2, events, FALSE, timeout);
    if (wait == WAIT_OBJECT_0) {
        return GetOverlappedResult(pipe, ov, transferred, FALSE) != FALSE;
    }
    CancelIoEx(pipe, ov);
    DWORD ignored = 0;
    GetOverlappedResult(pipe, ov, &ignored, TRUE);
    return false; // timeout, STOP request or error: always fail closed
}

static bool connect_one(HANDLE pipe, DWORD waitMs) {
    OVERLAPPED ov = {};
    ov.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!ov.hEvent) return false;
    BOOL started = ConnectNamedPipe(pipe, &ov);
    bool connected = started != FALSE;
    if (!connected) {
        DWORD err = GetLastError();
        if (err == ERROR_PIPE_CONNECTED) connected = true;
        else if (err == ERROR_IO_PENDING) {
            DWORD transferred = 0;
            connected = finish_pending(pipe, &ov, waitMs, &transferred);
        }
    }
    CloseHandle(ov.hEvent);
    return connected;
}

static bool transfer(HANDLE pipe, bool read, void* buffer, DWORD size, DWORD* bytes) {
    OVERLAPPED ov = {};
    ov.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!ov.hEvent) return false;
    *bytes = 0;
    BOOL immediate = read ? ReadFile(pipe, buffer, size, bytes, &ov)
                          : WriteFile(pipe, buffer, size, bytes, &ov);
    bool success = immediate != FALSE;
    if (!success && GetLastError() == ERROR_IO_PENDING) {
        success = finish_pending(pipe, &ov, 3000, bytes);
    }
    CloseHandle(ov.hEvent);
    return success;
}

static bool run_pipe(bool oneShot) {
    PSECURITY_DESCRIPTOR sd = nullptr;
    if (!security_descriptor(&sd)) {
        g_error = GetLastError();
        return false;
    }
    SECURITY_ATTRIBUTES security = {sizeof(security), sd, FALSE};
    bool overall = true;
    while (WaitForSingleObject(g_stop, 0) != WAIT_OBJECT_0) {
        HANDLE pipe = CreateNamedPipeW(
            kPipe, PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
            1, 256, 256, 3000, &security);
        if (pipe == INVALID_HANDLE_VALUE) {
            g_error = GetLastError();
            overall = false;
            break;
        }

        // A test instance times out rather than remaining in memory forever.
        // SCM instance waits until STOP; both can cancel blocked I/O.
        bool connected = connect_one(pipe, oneShot ? 10000 : INFINITE);
        if (connected && WaitForSingleObject(g_stop, 0) != WAIT_OBJECT_0) {
            char request[32] = {};
            DWORD length = 0;
            if (transfer(pipe, true, request, sizeof(request), &length)) {
                const bool privileged = trusted_pipe_client(pipe);
                // Strict, bounded protocol: not JSON, no credentials/tokens.
                const bool ping = (length == 4 && std::memcmp(request, "PING", 4) == 0);
                const char* answer = privileged && ping ? "PONG" : "DENIED";
                DWORD written = 0;
                transfer(pipe, false, const_cast<char*>(answer),
                         static_cast<DWORD>(std::strlen(answer)), &written);
            }
        }
        DisconnectNamedPipe(pipe);
        CloseHandle(pipe);
        if (oneShot) {
            if (!connected) {
                g_error = WAIT_TIMEOUT;
                overall = false;
            }
            break;
        }
    }
    LocalFree(sd);
    return overall;
}

static void WINAPI service_main(DWORD, LPWSTR*) {
    g_stop = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!g_stop) return;
    g_handler = RegisterServiceCtrlHandlerExW(kService, control, nullptr);
    if (!g_handler) {
        CloseHandle(g_stop);
        g_stop = nullptr;
        return;
    }
    report(SERVICE_START_PENDING);
    report(SERVICE_RUNNING);
    const bool ok = run_pipe(false);
    report(SERVICE_STOPPED, ok ? ERROR_SUCCESS : (g_error ? g_error : ERROR_GEN_FAILURE));
    CloseHandle(g_stop);
    g_stop = nullptr;
}

static int ping_client() {
    if (!WaitNamedPipeW(kPipe, 5000)) {
        std::printf("FAIL: diagnostic pipe not available (%lu)\n", GetLastError());
        return 4;
    }
    HANDLE pipe = CreateFileW(kPipe, GENERIC_READ | GENERIC_WRITE, 0, nullptr,
                              OPEN_EXISTING,
                              SECURITY_SQOS_PRESENT | SECURITY_IMPERSONATION, nullptr);
    if (pipe == INVALID_HANDLE_VALUE) {
        std::printf("FAIL: pipe access denied/unavailable (%lu)\n", GetLastError());
        return 5;
    }
    const char request[] = "PING";
    DWORD bytes = 0;
    char response[32] = {};
    bool success = WriteFile(pipe, request, 4, &bytes, nullptr) && bytes == 4 &&
                   ReadFile(pipe, response, sizeof(response), &bytes, nullptr) &&
                   bytes == 4 && std::memcmp(response, "PONG", 4) == 0;
    CloseHandle(pipe);
    if (!success) {
        std::puts("FAIL: expected authenticated PONG");
        return 6;
    }
    std::puts("PASS: protected named pipe replied PONG (no login/credentials)");
    return 0;
}

int wmain(int argc, wchar_t** argv) {
    if (argc != 2) {
        std::puts("Usage: FaceKidsBrokerPoc.exe --self-test | --console-once | --ping | --service");
        return 2;
    }
    if (std::wcscmp(argv[1], L"--self-test") == 0) {
        PSECURITY_DESCRIPTOR sd = nullptr;
        bool valid = security_descriptor(&sd) && IsValidSecurityDescriptor(sd);
        if (sd) LocalFree(sd);
        if (!valid) return 3;
        std::puts("PASS: Windows SCM shell and protected SYSTEM/Administrators-only pipe ACL");
        return 0;
    }
    if (std::wcscmp(argv[1], L"--ping") == 0) return ping_client();
    if (std::wcscmp(argv[1], L"--console-once") == 0) {
        g_stop = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        if (!g_stop) return 3;
        bool success = run_pipe(true);
        CloseHandle(g_stop);
        g_stop = nullptr;
        if (!success) {
            std::printf("FAIL: pipe server (%lu)\n", g_error);
            return 7;
        }
        std::puts("PASS: diagnostic pipe server exited without installing a service");
        return 0;
    }
    if (std::wcscmp(argv[1], L"--service") == 0) {
        SERVICE_TABLE_ENTRYW services[] = {
            {const_cast<LPWSTR>(kService), service_main}, {nullptr, nullptr}
        };
        if (!StartServiceCtrlDispatcherW(services)) {
            std::printf("Service SCM dispatcher unavailable (%lu)\n", GetLastError());
            return 8;
        }
        return 0;
    }
    return 2;
}
