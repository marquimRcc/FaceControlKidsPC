// Windows Terminal Services reader for P0-6. This is a diagnostic,
// NOT an authorization endpoint. Never trust a username string as identity.
#pragma once
#include <windows.h>
#include <wtsapi32.h>
#include <sddl.h>
#include <cstdio>
#include <vector>
#include <string>

#pragma comment(lib, "wtsapi32.lib")
#pragma comment(lib, "advapi32.lib")

namespace facekids_wts {

enum class LockView { Locked, Unlocked, Inactive, Unknown };

// Fail-closed state interpretation (Windows 10/11 only).
// Windows 7/2008 R2 invert the lock flags; intentionally unsupported.
inline LockView interpret(WTS_CONNECTSTATE_CLASS connection, LONG flags) {
    if (connection != WTSActive) return LockView::Inactive;
    if (flags == WTS_SESSIONSTATE_LOCK) return LockView::Locked;
    if (flags == WTS_SESSIONSTATE_UNLOCK) return LockView::Unlocked;
    return LockView::Unknown;
}
inline const wchar_t* label(LockView view) {
    switch (view) {
        case LockView::Locked: return L"LOCKED";
        case LockView::Unlocked: return L"UNLOCKED";
        case LockView::Inactive: return L"INACTIVE";
        default: return L"UNKNOWN";
    }
}

inline LockView read_state(DWORD id) {
    LPWSTR buffer = nullptr;
    DWORD size = 0;
    LockView result = LockView::Unknown;
    if (WTSQuerySessionInformationW(WTS_CURRENT_SERVER_HANDLE, id, WTSSessionInfoEx, &buffer, &size)) {
        if (buffer && size >= sizeof(WTSINFOEXW)) {
            const auto* info = reinterpret_cast<const WTSINFOEXW*>(buffer);
            if (info->Level == 1 && info->Data.WTSInfoExLevel1.SessionId == id) {
                const auto& v = info->Data.WTSInfoExLevel1;
                result = interpret(v.SessionState, v.SessionFlags);
            }
        }
    }
    if (buffer) WTSFreeMemory(buffer);
    return result;
}

inline std::wstring read_name(DWORD id) {
    LPWSTR buffer = nullptr;
    DWORD size = 0;
    std::wstring result;
    if (WTSQuerySessionInformationW(WTS_CURRENT_SERVER_HANDLE, id, WTSUserName, &buffer, &size)
        && buffer && size >= sizeof(wchar_t) && buffer[0]) {
        result.assign(buffer, buffer + wcsnlen_s(buffer, size / sizeof(wchar_t)));
    }
    if (buffer) WTSFreeMemory(buffer);
    return result;
}

// WTSQueryUserToken requires LocalSystem + SeTcbPrivilege, unlike a
// normal administrator process. An unavailable token is UNKNOWN, NEVER
// proof that a session belongs to the requested user.
inline std::wstring read_token_sid(DWORD id) {
    HANDLE token = nullptr;
    if (!WTSQueryUserToken(id, &token) || !token) return {};
    DWORD required = 0;
    GetTokenInformation(token, TokenUser, nullptr, 0, &required);
    std::vector<BYTE> bytes(required);
    std::wstring result;
    if (required >= sizeof(TOKEN_USER) &&
        GetTokenInformation(token, TokenUser, bytes.data(), required, &required)) {
        auto* user = reinterpret_cast<TOKEN_USER*>(bytes.data());
        LPWSTR sid = nullptr;
        if (user->User.Sid && ConvertSidToStringSidW(user->User.Sid, &sid) && sid) {
            result.assign(sid);
            LocalFree(sid);
        }
    }
    CloseHandle(token);
    return result;
}

inline bool self_test() {
    return interpret(WTSActive, WTS_SESSIONSTATE_LOCK) == LockView::Locked
        && interpret(WTSActive, WTS_SESSIONSTATE_UNLOCK) == LockView::Unlocked
        && interpret(WTSActive, WTS_SESSIONSTATE_UNKNOWN) == LockView::Unknown
        && interpret(WTSDisconnected, WTS_SESSIONSTATE_LOCK) == LockView::Inactive
        && interpret(WTSConnected, WTS_SESSIONSTATE_UNLOCK) == LockView::Inactive
        && interpret(WTSListen, WTS_SESSIONSTATE_LOCK) == LockView::Inactive;
}

inline int dump_local_sessions() {
    PWTS_SESSION_INFOW sessions = nullptr;
    DWORD count = 0;
    if (!WTSEnumerateSessionsW(WTS_CURRENT_SERVER_HANDLE, 0, 1, &sessions, &count)) {
        std::printf("WTS enumeration unavailable (error %lu)\n", GetLastError());
        return 4;
    }
    std::puts("FaceKids WTS diagnostics: read-only, no authentication");
    for (DWORD i = 0; i < count; ++i) {
        const DWORD id = sessions[i].SessionId;
        const auto state = read_state(id);
        const auto user = read_name(id);
        // SID is ONLY read from an OS token when we are running under
        // the correct security context; display UNKNOWN otherwise.
        const auto sid = read_token_sid(id);
        std::wprintf(L"Session %lu | user=%ls | state=%ls | token_sid=%ls\n",
                     id, user.empty() ? L"(none)" : user.c_str(), label(state),
                     sid.empty() ? L"UNKNOWN (requires SYSTEM)" : sid.c_str());
    }
    if (sessions) WTSFreeMemory(sessions);
    return 0;
}
} // namespace facekids_wts
