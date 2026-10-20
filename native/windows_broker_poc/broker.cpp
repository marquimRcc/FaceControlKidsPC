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
#include "wts_diagnostic.h"
#include "session_guard.h"
#include "quota_store.h"
#include "quota_gate.h"
#include "facial_policy.h"
#include "usage_meter.h"
#include "camera_capability.h"
#include "camera_frame_probe.h"
#include "service_identity.h"
#include "ipc_contract.h"
#include <vector>
#include <string>

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

// The pipe DACL limits connects to SYSTEM or elevated administrators,
// but only an exact LocalSystem token may perform a PRECHECK.
// Membership in Administrators alone NEVER authorizes the precheck.
enum class CallerRole { None, Administrator, LocalSystem };
static CallerRole authenticated_pipe_client(HANDLE pipe) {
    if (!ImpersonateNamedPipeClient(pipe)) return CallerRole::None;
    CallerRole result = CallerRole::None;
    HANDLE token = nullptr;
    if (OpenThreadToken(GetCurrentThread(), TOKEN_QUERY, TRUE, &token)) {
        BYTE systemSid[SECURITY_MAX_SID_SIZE] = {};
        BYTE adminSid[SECURITY_MAX_SID_SIZE] = {};
        DWORD systemBytes=sizeof(systemSid), adminBytes=sizeof(adminSid);
        DWORD required=0;
        GetTokenInformation(token, TokenUser, nullptr, 0, &required);
        std::vector<BYTE> buffer(required);
        const bool valid = required >= sizeof(TOKEN_USER) &&
            GetTokenInformation(token, TokenUser, buffer.data(), required, &required) &&
            CreateWellKnownSid(WinLocalSystemSid, nullptr, systemSid, &systemBytes) &&
            CreateWellKnownSid(WinBuiltinAdministratorsSid, nullptr, adminSid, &adminBytes);
        if (valid) {
            const auto* user=reinterpret_cast<const TOKEN_USER*>(buffer.data());
            if (user->User.Sid && EqualSid(user->User.Sid, systemSid)) {
                result=CallerRole::LocalSystem;
            } else {
                BOOL enabled=FALSE;
                if (CheckTokenMembership(token, adminSid, &enabled) && enabled)
                    result=CallerRole::Administrator;
            }
        }
        CloseHandle(token);
    }
    if (!RevertToSelf()) return CallerRole::None;
    return result;
}

static std::wstring configured_target_sid() {
    wchar_t sid[256]={};
    DWORD bytes=sizeof(sid);
    LONG status=RegGetValueW(HKEY_LOCAL_MACHINE,
        L"SOFTWARE\\FaceControlKidsPC\\CredentialProvider",
        L"TargetUserSid", RRF_RT_REG_SZ, nullptr, sid, &bytes);
    if (status!=ERROR_SUCCESS) return {};
    const std::wstring result(sid);
    return facekids_guard::valid_local_account_sid(result) ? result : std::wstring{};
}

static void local_service_day(char (&day)[11]) {
    SYSTEMTIME now={};
    GetLocalTime(&now);
    sprintf_s(day, sizeof(day), "%04u-%02u-%02u",
              now.wYear, now.wMonth, now.wDay);
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

static bool run_pipe(bool oneShot, facekids_quota::Store* quotas = nullptr,
                     const std::wstring& target_sid = L"",
                     const facekids_camera::DeviceInventory* camera = nullptr) {
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
                const CallerRole role = authenticated_pipe_client(pipe);
                const bool ping = length == 4 && std::memcmp(request, "PING", 4) == 0;
                const bool askCamera = length == 4 &&
                    std::memcmp(request, "CAM?", 4) == 0;
                const char* answer="DENIED";
                if (ping && role != CallerRole::None) {
                    answer="PONG";
                } else if (askCamera && role != CallerRole::None && camera) {
                    switch (camera->capability) {
                        case facekids_camera::Capability::NoCamera:
                            answer="CAMERA_NONE"; break;
                        case facekids_camera::Capability::EnumeratedOnly:
                            answer="CAMERA_ENUMERATED"; break;
                        default: answer="CAMERA_UNAVAILABLE"; break;
                    }
                } else {
                    facekids_ipc::Request parsed={};
                    const bool valid=facekids_ipc::parse(
                        request, length, &parsed)==facekids_ipc::ParseResult::Valid;
                    // Precheck is protected by the SYSTEM *user token*,
                    // not by an untrusted SID/identity supplied over IPC.
                    if (valid && role == CallerRole::Administrator &&
                        quotas && parsed.command == facekids_ipc::kEraseTemplates) {
                        int erased=0;
                        if (quotas->erase_templates(static_cast<int>(parsed.child_id),&erased))
                            answer="ERASED"; // never send face template bytes
                    } else if (valid && role == CallerRole::LocalSystem &&
                        parsed.command == facekids_ipc::kPrecheck &&
                        quotas && !target_sid.empty()) {
                        char day[11]={};
                        local_service_day(day);
                        auto gate=facekids_gate::check_live_wts(
                            parsed.session_id, target_sid, *quotas,
                            static_cast<int>(parsed.child_id), day);
                        if (gate==facekids_gate::GatePrerequisite::ReadyForFacialPolicy)
                            answer="PRECHECK_ONLY"; // NEVER a logon ticket
                    }
                }
                DWORD written=0;
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
    // A misconfigured SCM account must never expose the protected broker.
    // Elevated Administrators are NOT equivalent to LocalSystem.
    if (facekids_service_identity::current_process_identity() !=
        facekids_service_identity::ServiceIdentity::LocalSystem) {
        report(SERVICE_STOPPED, ERROR_ACCESS_DENIED);
        CloseHandle(g_stop);
        g_stop = nullptr;
        return;
    }
    // Service-only persistent quota DB. This path is NEVER touched by tests,
    // --sessions or any unprivileged client operation.
    facekids_quota::Store quotas;
    const std::wstring root = facekids_quota::program_data_root();
    if (root.empty() || !quotas.open(root)) {
        report(SERVICE_STOPPED, ERROR_ACCESS_DENIED);
        CloseHandle(g_stop);
        g_stop = nullptr;
        return; // fail closed: no service pipe without a protected quota DB
    }
    // Device enumeration is performed in the actual LocalSystem process.
    // Presence is informational ONLY: it is NOT liveness, face identity
    // or evidence valid for the internal facial authorization model.
    const auto camera = facekids_camera::enumerate();
    report(SERVICE_RUNNING);
    const std::wstring sid = configured_target_sid();
    // No target SID: diagnostic health PING remains possible, all
    // PRECHECK requests are denied, including those from SYSTEM.
    const bool ok = run_pipe(false, &quotas, sid, &camera);
    report(SERVICE_STOPPED, ok ? ERROR_SUCCESS : (g_error ? g_error : ERROR_GEN_FAILURE));
    CloseHandle(g_stop);
    g_stop = nullptr;
}

// Real ACL regression against the file created by the LocalSystem
// service on an EPHEMERAL Windows test runner. No child accounts created.
static int restricted_token_database_client() {
    const std::wstring db=facekids_quota::program_data_root()+L"\\quota.sqlite3";
    if (GetFileAttributesW(db.c_str())==INVALID_FILE_ATTRIBUTES) {
        std::puts("FAIL: protected quota DB not present");
        return 4;
    }
    HANDLE token=nullptr, reduced=nullptr;
    BYTE administratorsSid[SECURITY_MAX_SID_SIZE]={};
    DWORD bytes=sizeof(administratorsSid);
    if (!CreateWellKnownSid(WinBuiltinAdministratorsSid,nullptr,
                            administratorsSid,&bytes) ||
        !OpenProcessToken(GetCurrentProcess(),
                          TOKEN_DUPLICATE|TOKEN_QUERY,&token)) {
        if(token) CloseHandle(token);
        return 5;
    }
    SID_AND_ATTRIBUTES disabled={administratorsSid,0};
    bool ok=CreateRestrictedToken(token, DISABLE_MAX_PRIVILEGE,
                                   1,&disabled,0,nullptr,0,nullptr,&reduced)!=FALSE;
    CloseHandle(token);
    if(!ok || !reduced) {
        if(reduced) CloseHandle(reduced);
        return 6;
    }
    if(!ImpersonateLoggedOnUser(reduced)) {
        CloseHandle(reduced);
        return 7;
    }
    HANDLE file=CreateFileW(db.c_str(),GENERIC_READ|GENERIC_WRITE,
                            FILE_SHARE_READ|FILE_SHARE_WRITE,
                            nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    const DWORD error=file==INVALID_HANDLE_VALUE?GetLastError():ERROR_SUCCESS;
    if(file!=INVALID_HANDLE_VALUE) CloseHandle(file);
    const bool reverted=RevertToSelf()!=FALSE;
    CloseHandle(reduced);
    if(!reverted || error!=ERROR_ACCESS_DENIED) {
        std::printf("FAIL: restricted token had protected database access (%lu)\n",error);
        return 8;
    }
    std::puts("PASS: restricted child-like token denied access to native face/quota DB");
    return 0;
}

// Simulate a standard child account without creating Windows users:
// disable Administrators group membership and privileges in a restricted
// OS-issued token, then verify the server DACL rejects the connection.
static int restricted_token_pipe_client() {
    if (!WaitNamedPipeW(kPipe, 5000)) return 4;
    HANDLE token=nullptr, reduced=nullptr;
    BYTE administratorsSid[SECURITY_MAX_SID_SIZE]={};
    DWORD bytes=sizeof(administratorsSid);
    if (!CreateWellKnownSid(WinBuiltinAdministratorsSid, nullptr,
                            administratorsSid, &bytes) ||
        !OpenProcessToken(GetCurrentProcess(), TOKEN_DUPLICATE|TOKEN_QUERY, &token)) {
        if (token) CloseHandle(token);
        return 5;
    }
    SID_AND_ATTRIBUTES disabled={administratorsSid,0};
    const bool created=CreateRestrictedToken(token, DISABLE_MAX_PRIVILEGE,
        1, &disabled, 0, nullptr, 0, nullptr, &reduced) != FALSE;
    CloseHandle(token);
    if (!created || !reduced) {
        if(reduced) CloseHandle(reduced);
        return 6;
    }
    if (!ImpersonateLoggedOnUser(reduced)) {
        CloseHandle(reduced);
        return 7;
    }
    HANDLE pipe=CreateFileW(kPipe, GENERIC_READ|GENERIC_WRITE, 0, nullptr,
        OPEN_EXISTING, SECURITY_SQOS_PRESENT|SECURITY_IMPERSONATION, nullptr);
    DWORD error=pipe==INVALID_HANDLE_VALUE ? GetLastError() : ERROR_SUCCESS;
    if (pipe!=INVALID_HANDLE_VALUE) CloseHandle(pipe);
    const bool reverted=RevertToSelf()!=FALSE;
    CloseHandle(reduced);
    if (!reverted || error!=ERROR_ACCESS_DENIED) {
        std::printf("FAIL: restricted token had unexpected pipe access (%lu)\n",error);
        return 8;
    }
    std::puts("PASS: restricted non-admin Windows token denied by named-pipe ACL");
    return 0;
}

// Explicit local parental maintenance. The broker verifies the actual
// elevated Windows administrator token and never accepts this from Filhos.
static int erase_templates_admin_client(int child) {
    if(child<1 || child>3 || !WaitNamedPipeW(kPipe,5000)) return 4;
    HANDLE pipe=CreateFileW(kPipe,GENERIC_READ|GENERIC_WRITE,0,nullptr,
        OPEN_EXISTING,SECURITY_SQOS_PRESENT|SECURITY_IMPERSONATION,nullptr);
    if(pipe==INVALID_HANDLE_VALUE) return 5;
    facekids_ipc::Request request={};
    request.command=facekids_ipc::kEraseTemplates;
    request.session_id=0;
    request.child_id=static_cast<uint32_t>(child);
    DWORD written=0,received=0;
    char answer[32]={};
    const bool success=WriteFile(pipe,&request,sizeof(request),&written,nullptr) &&
        written==sizeof(request) &&
        ReadFile(pipe,answer,sizeof(answer),&received,nullptr) &&
        received==6 && std::memcmp(answer,"ERASED",6)==0;
    CloseHandle(pipe);
    if(!success) {
        std::puts("FAIL: administrator template erase was denied or unavailable");
        return 6;
    }
    std::printf("PASS: protected broker erased templates for profile %d (no login)\n",child);
    return 0;
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

static int camera_status_client() {
    if (!WaitNamedPipeW(kPipe, 5000)) return 4;
    HANDLE h=CreateFileW(kPipe, GENERIC_READ|GENERIC_WRITE, 0, nullptr,
        OPEN_EXISTING, SECURITY_SQOS_PRESENT|SECURITY_IMPERSONATION, nullptr);
    if (h==INVALID_HANDLE_VALUE) return 5;
    DWORD written=0, received=0;
    char buffer[32]={};
    bool ok=WriteFile(h, "CAM?", 4, &written, nullptr) && written==4 &&
        ReadFile(h, buffer, sizeof(buffer), &received, nullptr);
    CloseHandle(h);
    // Positive enumeration means hardware visible, NOT liveness.
    const bool expected=ok && (
        (received==11 && std::memcmp(buffer,"CAMERA_NONE",11)==0) ||
        (received==17 && std::memcmp(buffer,"CAMERA_ENUMERATED",17)==0) ||
        (received==18 && std::memcmp(buffer,"CAMERA_UNAVAILABLE",18)==0));
    if (!expected) {
        std::puts("FAIL: protected camera inventory query unavailable");
        return 6;
    }
    std::printf("PASS: service-side camera capability = %.*s (no image/authentication)\\n",
                static_cast<int>(received), buffer);
    return 0;
}

// Oversized frames MUST NOT be interpreted as a valid precheck.
// The message-mode pipe can reply DENIED or close the connection;
// both are safe, but PRECHECK_ONLY or PONG would be a critical defect.
static int oversized_request_client() {
    if (!WaitNamedPipeW(kPipe, 5000)) return 4;
    HANDLE pipe=CreateFileW(kPipe, GENERIC_READ|GENERIC_WRITE, 0, nullptr,
        OPEN_EXISTING, SECURITY_SQOS_PRESENT|SECURITY_IMPERSONATION, nullptr);
    if (pipe==INVALID_HANDLE_VALUE) return 5;
    BYTE message[128]={};
    facekids_ipc::Request request={};
    request.session_id=7;
    request.child_id=1;
    std::memcpy(message, &request, sizeof(request));
    DWORD written=0, received=0;
    char response[32]={};
    bool sent=WriteFile(pipe, message, sizeof(message), &written, nullptr)
        && written==sizeof(message);
    bool answered=sent && ReadFile(pipe, response, sizeof(response), &received, nullptr);
    CloseHandle(pipe);
    if (!sent) return 6;
    if (answered && (received!=6 || std::memcmp(response,"DENIED",6)!=0)) {
        std::puts("FAIL: oversized precheck received unsafe response");
        return 7;
    }
    std::puts("PASS: oversized IPC request denied or disconnected (no grant)");
    return 0;
}

// Exercise malformed protocol bytes across a real named-pipe connection.
// The broker must return DENIED without accessing quota or Windows login.
static int malformed_request_client() {
    if (!WaitNamedPipeW(kPipe, 5000)) return 4;
    HANDLE pipe=CreateFileW(kPipe, GENERIC_READ|GENERIC_WRITE, 0, nullptr,
                            OPEN_EXISTING,
                            SECURITY_SQOS_PRESENT|SECURITY_IMPERSONATION, nullptr);
    if (pipe==INVALID_HANDLE_VALUE) return 5;
    facekids_ipc::Request request={};
    request.magic=0; // invalid even though the remaining fields are plausible
    request.session_id=7;
    request.child_id=1;
    DWORD sent=0, received=0;
    char response[32]={};
    bool ok=WriteFile(pipe, &request, sizeof(request), &sent, nullptr)
        && sent==sizeof(request)
        && ReadFile(pipe, response, sizeof(response), &received, nullptr);
    CloseHandle(pipe);
    if (!ok || received!=6 || std::memcmp(response,"DENIED",6)!=0) {
        std::puts("FAIL: malformed protocol was not explicitly denied");
        return 6;
    }
    std::puts("PASS: malformed binary protocol denied across named pipe");
    return 0;
}

static int negative_precheck_client() {
    if (!WaitNamedPipeW(kPipe, 5000)) return 4;
    HANDLE pipe=CreateFileW(kPipe, GENERIC_READ|GENERIC_WRITE, 0, nullptr,
        OPEN_EXISTING, SECURITY_SQOS_PRESENT|SECURITY_IMPERSONATION, nullptr);
    if (pipe==INVALID_HANDLE_VALUE) return 5;
    DWORD session=0, written=0, read=0;
    char response[32]={};
    ProcessIdToSessionId(GetCurrentProcessId(), &session);
    facekids_ipc::Request request={};
    request.session_id=session ? session : 1;
    request.child_id=1;
    const bool sent=WriteFile(pipe,&request,sizeof(request),&written,nullptr) &&
        written==sizeof(request);
    const bool got=sent && ReadFile(pipe,response,sizeof(response),&read,nullptr);
    CloseHandle(pipe);
    if (!got || read!=6 || std::memcmp(response,"DENIED",6)!=0) {
        std::puts("FAIL: precheck must reject interactive admin caller");
        return 6;
    }
    std::puts("PASS: precheck denies interactive admin (no credentials)");
    return 0;
}

static bool facial_policy_self_test() {
    // Isolated ACL-protected SQLite DB with three fresh child quotas;
    // tests never write to ProgramData or create a real credential.
    wchar_t temporary[MAX_PATH]={}, unique[MAX_PATH]={};
    if (!GetTempPathW(MAX_PATH, temporary) ||
        !GetTempFileNameW(temporary, L"FPL", 0, unique) ||
        !DeleteFileW(unique)) return false;
    const std::wstring root(unique);
    if (!facekids_quota::make_secure_directory(root)) return false;
    bool passed=false;
    {
        facekids_quota::Store database;
        passed=database.open(root) && facekids_face::self_test(database);
    }
    DeleteFileW((root + L"\\quota.sqlite3").c_str());
    RemoveDirectoryW(root.c_str());
    return passed;
}

static bool usage_meter_self_test() {
    // Independent temporary ACL-protected SQLite DB; no live child session
    // or WTS control, Windows login, and no installed SCM changes.
    wchar_t temporary[MAX_PATH]={},unique[MAX_PATH]={};
    if(!GetTempPathW(MAX_PATH,temporary) ||
       !GetTempFileNameW(temporary,L"FUM",0,unique) ||
       !DeleteFileW(unique)) return false;
    const std::wstring root(unique);
    if(!facekids_quota::make_secure_directory(root)) return false;
    bool passed=false;
    {
        facekids_quota::Store quota;
        passed=quota.open(root) && facekids_usage::self_test(quota);
    }
    DeleteFileW((root+L"\\quota.sqlite3").c_str());
    RemoveDirectoryW(root.c_str());
    return passed;
}

static bool quota_gate_self_test() {
    wchar_t temporary[MAX_PATH] = {};
    wchar_t unique[MAX_PATH] = {};
    if (!GetTempPathW(MAX_PATH, temporary) ||
        !GetTempFileNameW(temporary, L"FQP", 0, unique) ||
        !DeleteFileW(unique)) return false;
    const std::wstring root(unique);
    if (!facekids_quota::make_secure_directory(root)) return false;
    bool passed = false;
    {
        facekids_quota::Store database;
        passed = database.open(root) && facekids_gate::self_test(database);
    }
    DeleteFileW((root + L"\\quota.sqlite3").c_str());
    RemoveDirectoryW(root.c_str());
    return passed;
}

int wmain(int argc, wchar_t** argv) {
    if (argc == 3 && std::wcscmp(argv[1],L"--erase-templates")==0) {
        if(std::wcslen(argv[2])!=1 || argv[2][0]<L'1' || argv[2][0]>L'3')
            return 2;
        return erase_templates_admin_client(int(argv[2][0]-L'0'));
    }
    if (argc != 2) {
        std::puts("Usage: FaceKidsBrokerPoc.exe --self-test | --service-identity | --camera-capability | --frame-probe | --sessions | --console-once | --ping | --restricted-token-test | --restricted-db-test | --erase-templates 1..3 | --camera-status | --precheck-as-admin | --malformed-request | --oversized-request | --service");
        return 2;
    }
    if (std::wcscmp(argv[1], L"--service-identity") == 0) {
        const auto id=facekids_service_identity::current_process_identity();
        if (id==facekids_service_identity::ServiceIdentity::LocalSystem)
            std::puts("SYSTEM");
        else if (id==facekids_service_identity::ServiceIdentity::NotLocalSystem)
            std::puts("NOT_SYSTEM");
        else std::puts("IDENTITY_UNAVAILABLE");
        return id==facekids_service_identity::ServiceIdentity::Unavailable ? 4 : 0;
    }
    if (std::wcscmp(argv[1], L"--frame-probe") == 0) {
        // Opt-in physical-camera diagnostic ONLY; never entered from service.
        const auto measured=facekids_frame::capture_one_frame();
        const char* label=measured.status==facekids_frame::Status::FrameMeasured
          ? (measured.nonuniform ? "FRAME_OK_NONUNIFORM" : "FRAME_OK_UNIFORM")
          : measured.status==facekids_frame::Status::NoCamera
            ? "NO_CAMERA" : "CAPTURE_UNAVAILABLE";
        std::printf("FaceKids opt-in frame check: %s | hr=0x%08lx\\n",
                    label, static_cast<unsigned long>(measured.hr));
        std::puts("Diagnostic only. No frames saved and NO facial authentication.");
        return 0;
    }
    if (std::wcscmp(argv[1], L"--camera-capability") == 0) {
        const auto inventory=facekids_camera::enumerate();
        std::printf("FaceKids Windows camera capability: %s | devices=%u | hr=0x%08lx\n",
                    facekids_camera::describe(inventory.capability),
                    inventory.device_count, static_cast<unsigned long>(inventory.code));
        std::puts("No image sampled, no face recognition, no login authorization.");
        return inventory.usable_for_authentication() ? 3 : 0;
    }
    if (std::wcscmp(argv[1], L"--sessions") == 0)
        return facekids_wts::dump_local_sessions();
    if (std::wcscmp(argv[1], L"--self-test") == 0) {
        PSECURITY_DESCRIPTOR sd = nullptr;
        bool valid = security_descriptor(&sd) && IsValidSecurityDescriptor(sd);
        if (sd) LocalFree(sd);
        if (!valid || !facekids_wts::self_test() || !facekids_guard::self_test() ||
            !facekids_quota::self_test() || !quota_gate_self_test() ||
            !facekids_ipc::self_test() || !facial_policy_self_test() ||
            !facekids_camera::self_test() ||
            !facekids_frame::self_test() ||
            !usage_meter_self_test() ||
            !facekids_service_identity::self_test()) return 3;
        std::puts("PASS: SCM, ACL-restricted pipe and SQLite, WTS, facial readiness internal simulation");
        return 0;
    }
    if (std::wcscmp(argv[1], L"--ping") == 0) return ping_client();
    if (std::wcscmp(argv[1], L"--restricted-token-test") == 0) return restricted_token_pipe_client();
    if (std::wcscmp(argv[1], L"--restricted-db-test") == 0) return restricted_token_database_client();
    if (std::wcscmp(argv[1], L"--camera-status") == 0) return camera_status_client();
    if (std::wcscmp(argv[1], L"--precheck-as-admin") == 0) return negative_precheck_client();
    if (std::wcscmp(argv[1], L"--malformed-request") == 0) return malformed_request_client();
    if (std::wcscmp(argv[1], L"--oversized-request") == 0) return oversized_request_client();
    if (std::wcscmp(argv[1], L"--console-once") == 0) {
        g_stop = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        if (!g_stop) return 3;
        const auto camera=facekids_camera::enumerate();
        bool success = run_pipe(true, nullptr, L"", &camera);
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
