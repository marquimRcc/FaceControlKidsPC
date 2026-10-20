// P0-8b: policy prerequisites combine trusted Windows WTS SID and SQLite
// quotas. This is NOT permission to log on and never produces credentials.
#pragma once
#include "session_guard.h"
#include "quota_store.h"
#include <string>

namespace facekids_gate {

enum class GatePrerequisite {
    ReadyForFacialPolicy, // NOT a Windows authentication grant
    SessionDenied,
    QuotaUnavailable,
    QuotaExhausted
};

inline GatePrerequisite check(
    const facekids_guard::Snapshot& os_session,
    const std::wstring& expected_windows_sid,
    facekids_quota::Store& quota,
    int child_id,
    const char* trusted_local_day) {
    if (facekids_guard::check_snapshot(os_session, expected_windows_sid)
        != facekids_guard::Verdict::ReadyForPolicyCheck) {
        return GatePrerequisite::SessionDenied;
    }
    sqlite3_int64 remaining = 0;
    if (!quota.remaining(child_id, trusted_local_day, &remaining))
        return GatePrerequisite::QuotaUnavailable;
    return remaining > 0
        ? GatePrerequisite::ReadyForFacialPolicy
        : GatePrerequisite::QuotaExhausted;
}

// This is the only suitable function for the future LocalSystem service.
// WTSQueryUserToken may fail for interactive callers; failure denies.
// The caller must derive trusted_local_day from the service's clock.
inline GatePrerequisite check_live_wts(
    DWORD session_id,
    const std::wstring& expected_windows_sid,
    facekids_quota::Store& quota,
    int child_id,
    const char* trusted_local_day) {
    if (facekids_guard::inspect_real_session(session_id, expected_windows_sid)
        != facekids_guard::Verdict::ReadyForPolicyCheck) {
        return GatePrerequisite::SessionDenied;
    }
    sqlite3_int64 remaining = 0;
    if (!quota.remaining(child_id, trusted_local_day, &remaining))
        return GatePrerequisite::QuotaUnavailable;
    return remaining > 0
        ? GatePrerequisite::ReadyForFacialPolicy
        : GatePrerequisite::QuotaExhausted;
}

inline bool self_test(facekids_quota::Store& quota) {
    constexpr auto Locked = facekids_wts::LockView::Locked;
    const std::wstring sid = L"S-1-5-21-100-200-300-1005";
    const std::wstring admin = L"S-1-5-21-100-200-300-1001";
    facekids_guard::Snapshot session = {7, 7, Locked, sid, true};
    const char* day = "2026-10-20";
    if (check(session, sid, quota, 1, day) != GatePrerequisite::ReadyForFacialPolicy)
        return false;
    if (!quota.charge(1, day, 7200)) return false;
    if (check(session, sid, quota, 1, day) != GatePrerequisite::QuotaExhausted)
        return false;
    if (check(session, sid, quota, 2, day) != GatePrerequisite::ReadyForFacialPolicy)
        return false;
    if (!quota.charge(2, day, 7200)) return false;
    if (check(session, sid, quota, 2, day) != GatePrerequisite::QuotaExhausted)
        return false;
    if (check(session, sid, quota, 3, day) != GatePrerequisite::ReadyForFacialPolicy)
        return false;
    if (check(session, admin, quota, 3, day) != GatePrerequisite::SessionDenied)
        return false;
    session.state = facekids_wts::LockView::Unlocked;
    if (check(session, sid, quota, 3, day) != GatePrerequisite::SessionDenied)
        return false;
    session.state = Locked;
    session.token_from_os = false;
    if (check(session, sid, quota, 3, day) != GatePrerequisite::SessionDenied)
        return false;
    session.token_from_os = true;
    if (check(session, sid, quota, 0, day) != GatePrerequisite::QuotaUnavailable)
        return false;
    // The next checks use child 3, which still has positive quota.
    // No WTS transition may inherit a previous successful precheck.
    if (check(session, sid, quota, 3, day) != GatePrerequisite::ReadyForFacialPolicy)
        return false;
    session.state = facekids_wts::LockView::Inactive;
    if (check(session, sid, quota, 3, day) != GatePrerequisite::SessionDenied)
        return false;
    session.state = facekids_wts::LockView::Unknown;
    if (check(session, sid, quota, 3, day) != GatePrerequisite::SessionDenied)
        return false;
    session.state = Locked;
    session.actual_id = 8; // session switched since face capture
    if (check(session, sid, quota, 3, day) != GatePrerequisite::SessionDenied)
        return false;
    session.actual_id = 7;
    session.token_sid = admin; // other Windows identity
    if (check(session, sid, quota, 3, day) != GatePrerequisite::SessionDenied)
        return false;
    session.token_sid = sid;
    if (check(session, sid, quota, 3, "2026-02-30") != GatePrerequisite::QuotaUnavailable)
        return false;
    if (check(session, sid, quota, 3, day) != GatePrerequisite::ReadyForFacialPolicy)
        return false;
    return true;
}

} // namespace facekids_gate
