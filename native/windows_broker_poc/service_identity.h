// P0-15: the Windows broker service MUST run as NT AUTHORITY\SYSTEM.
// A caller that is merely an administrator (even elevated) cannot act as
// the privileged broker. Compare the process token user SID from Windows,
// not the display name, environment, pipe caller or group membership.
#pragma once
#include <windows.h>
#include <sddl.h>

namespace facekids_service_identity {

enum class ServiceIdentity { LocalSystem, NotLocalSystem, Unavailable };

inline bool is_system_sid(PSID sid) {
    if (!sid || !IsValidSid(sid)) return false;
    BYTE known[SECURITY_MAX_SID_SIZE]={};
    DWORD bytes=sizeof(known);
    return CreateWellKnownSid(WinLocalSystemSid, nullptr, known, &bytes) &&
           EqualSid(sid, known) != FALSE;
}

inline ServiceIdentity current_process_identity() {
    HANDLE token=nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token))
        return ServiceIdentity::Unavailable;
    DWORD bytes=0;
    GetTokenInformation(token, TokenUser, nullptr, 0, &bytes);
    ServiceIdentity result=ServiceIdentity::Unavailable;
    if (bytes >= sizeof(TOKEN_USER) && bytes <= 65536) {
        auto* buffer=static_cast<BYTE*>(LocalAlloc(LPTR, bytes));
        if (buffer) {
            if (GetTokenInformation(token, TokenUser, buffer, bytes, &bytes)) {
                auto* user=reinterpret_cast<TOKEN_USER*>(buffer);
                result=is_system_sid(user->User.Sid)
                       ? ServiceIdentity::LocalSystem
                       : ServiceIdentity::NotLocalSystem;
            }
            LocalFree(buffer);
        }
    }
    CloseHandle(token);
    return result;
}

inline bool self_test() {
    PSID admin=nullptr;
    PSID system=nullptr;
    bool pass=ConvertStringSidToSidW(L"S-1-5-32-544", &admin) &&
              ConvertStringSidToSidW(L"S-1-5-18", &system);
    pass=pass && is_system_sid(system) && !is_system_sid(admin) &&
         !is_system_sid(nullptr);
    if (admin) LocalFree(admin);
    if (system) LocalFree(system);
    return pass;
}

} // namespace facekids_service_identity
