// P0-7: trustworthy WTS gate prerequisite for the future Windows broker.
// A "Ready" decision is NOT an unlock authorization or credential.
// Only trusted service-side code may call inspect_real_session().
#pragma once
#include "wts_diagnostic.h"
#include <windows.h>
#include <sddl.h>
#include <string>
#include <cstring>

namespace facekids_guard {

enum class Verdict {
    ReadyForPolicyCheck,  // NOT a grant, only WTS identity/state prerequisites
    InvalidSession,
    InvalidTargetSid,
    UnknownSessionState,
    NotLocked,
    UnverifiedToken,
    WrongAccount
};

inline const char* label(Verdict value) {
    switch (value) {
        case Verdict::ReadyForPolicyCheck: return "READY_FOR_POLICY_ONLY";
        case Verdict::InvalidSession: return "INVALID_SESSION";
        case Verdict::InvalidTargetSid: return "INVALID_TARGET_SID";
        case Verdict::UnknownSessionState: return "UNKNOWN_SESSION_STATE";
        case Verdict::NotLocked: return "NOT_LOCKED";
        case Verdict::UnverifiedToken: return "UNVERIFIED_OS_TOKEN";
        case Verdict::WrongAccount: return "WRONG_ACCOUNT";
        default: return "DENIED";
    }
}

struct Snapshot {
    DWORD requested_id = 0;
    DWORD actual_id = 0;
    facekids_wts::LockView state = facekids_wts::LockView::Unknown;
    // This string may ONLY come from OS WTSQueryUserToken -> TokenUser.
    std::wstring token_sid;
    bool token_from_os = false;
};

// Accept only machine-local style account SIDs, not SYSTEM, service or groups.
inline bool valid_local_account_sid(const std::wstring& value) {
    if (value.rfind(L"S-1-5-21-", 0) != 0 || value.size() > 160) return false;
    PSID sid = nullptr;
    if (!ConvertStringSidToSidW(value.c_str(), &sid) || !sid) return false;
    bool ok = IsValidSid(sid) && *GetSidSubAuthorityCount(sid) == 5;
    LocalFree(sid);
    return ok;
}

inline bool sid_equals(const std::wstring& left, const std::wstring& right) {
    PSID a = nullptr, b = nullptr;
    const bool first = ConvertStringSidToSidW(left.c_str(), &a) != FALSE;
    const bool second = ConvertStringSidToSidW(right.c_str(), &b) != FALSE;
    const bool eq = first && second && a && b && EqualSid(a, b) != FALSE;
    if (a) LocalFree(a);
    if (b) LocalFree(b);
    return eq;
}

// Snapshot is an injected test input, NEVER a client-supplied IPC payload.
inline Verdict check_snapshot(const Snapshot& record, const std::wstring& target_sid) {
    if (record.requested_id == 0 || record.requested_id == 0xffffffff ||
        record.requested_id != record.actual_id) return Verdict::InvalidSession;
    if (!valid_local_account_sid(target_sid)) return Verdict::InvalidTargetSid;
    if (record.state == facekids_wts::LockView::Unknown)
        return Verdict::UnknownSessionState;
    if (record.state != facekids_wts::LockView::Locked)
        return Verdict::NotLocked;
    if (!record.token_from_os || !valid_local_account_sid(record.token_sid))
        return Verdict::UnverifiedToken;
    if (!sid_equals(record.token_sid, target_sid)) return Verdict::WrongAccount;
    return Verdict::ReadyForPolicyCheck;
}

// Produces the snapshot from WTS APIs; does not accept identity from clients.
// The WTSQueryUserToken step generally requires LocalSystem and SeTcbPrivilege.
// On the parent's interactive desktop it should fail CLOSED.
inline Verdict inspect_real_session(DWORD session_id, const std::wstring& target_sid) {
    if (session_id == 0 || session_id == 0xffffffff) return Verdict::InvalidSession;
    Snapshot snapshot;
    snapshot.requested_id = session_id;
    snapshot.actual_id = session_id;
    snapshot.state = facekids_wts::read_state(session_id);
    snapshot.token_sid = facekids_wts::read_token_sid(session_id);
    snapshot.token_from_os = !snapshot.token_sid.empty();
    return check_snapshot(snapshot, target_sid);
}

inline bool self_test() {
    constexpr auto Locked = facekids_wts::LockView::Locked;
    constexpr auto Unlocked = facekids_wts::LockView::Unlocked;
    constexpr auto Unknown = facekids_wts::LockView::Unknown;
    constexpr auto Inactive = facekids_wts::LockView::Inactive;
    const std::wstring child = L"S-1-5-21-100-200-300-1005";
    const std::wstring parent = L"S-1-5-21-100-200-300-1001";
    Snapshot s = {7, 7, Locked, child, true};
    if (!valid_local_account_sid(child) || valid_local_account_sid(L"Filhos") ||
        valid_local_account_sid(L"S-1-5-18") ||
        !sid_equals(child, L"S-1-5-21-100-200-300-1005")) return false;
    if (check_snapshot(s, child) != Verdict::ReadyForPolicyCheck ||
        check_snapshot(s, parent) != Verdict::WrongAccount) return false;
    s.state = Unlocked;
    if (check_snapshot(s, child) != Verdict::NotLocked) return false;
    s.state = Inactive;
    if (check_snapshot(s, child) != Verdict::NotLocked) return false;
    s.state = Unknown;
    if (check_snapshot(s, child) != Verdict::UnknownSessionState) return false;
    s.state = Locked;
    s.token_from_os = false;
    if (check_snapshot(s, child) != Verdict::UnverifiedToken) return false;
    s.token_from_os = true;
    s.token_sid.clear();
    if (check_snapshot(s, child) != Verdict::UnverifiedToken) return false;
    s.token_sid = parent;
    if (check_snapshot(s, child) != Verdict::WrongAccount) return false;
    s.token_sid = child;
    s.actual_id = 8;
    if (check_snapshot(s, child) != Verdict::InvalidSession) return false;
    s.actual_id = 7;
    if (check_snapshot(s, L"") != Verdict::InvalidTargetSid) return false;
    s.requested_id = 0;
    if (check_snapshot(s, child) != Verdict::InvalidSession) return false;
    return true;
}

} // namespace facekids_guard
