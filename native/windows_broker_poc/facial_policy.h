// P0-12: internal policy connecting SYNTHETIC facial evidence and trusted
// WTS + protected SQLite quota checks. NEVER a Windows authentication grant.
// EvidenceOrigin is a test seam, not cryptographic proof of sensor provenance.
#pragma once
#include "quota_gate.h"
#include <windows.h>
#include <mutex>
#include <string>

namespace facekids_face {

enum class EvidenceOrigin { Unknown, ProtectedWorker };
enum class Decision {
    PendingInternalRecheck,
    ReadyForAdditionalControls, // NOT a login/unlock grant
    DeniedUntrustedOrigin,
    DeniedCameraOrFace,
    DeniedStaleCapture,
    DeniedNoQuotaOrSession,
    DeniedNoPending,
    DeniedExpiredOrWrongSession
};

struct WorkerObservation {
    int child_id = 0;
    DWORD session_id = 0;
    int faces = 0;
    int confirmations = 0;
    bool camera_healthy = false;
    bool liveness_passed = false;
    EvidenceOrigin origin = EvidenceOrigin::Unknown;
    ULONGLONG captured_tick_ms = 0;
};

inline bool valid_observation(const WorkerObservation& e, ULONGLONG now_ms) {
    return e.child_id >= 1 && e.child_id <= 3 &&
           e.session_id != 0 && e.session_id != 0xffffffff &&
           e.faces == 1 && e.confirmations >= 3 &&
           e.camera_healthy && e.liveness_passed &&
           now_ms >= e.captured_tick_ms &&
           now_ms - e.captured_tick_ms <= 3000;
}

// No child-facing IPC operation can invoke these methods in the current
// broker. Only a future protected in-process camera worker may do so.
class InternalFacePolicy {
    std::mutex lock_;
    int pending_child_ = 0;
    DWORD pending_session_ = 0;
    ULONGLONG issued_at_ = 0;
    void clear() {
        pending_child_ = 0;
        pending_session_ = 0;
        issued_at_ = 0;
    }
public:
    InternalFacePolicy() = default;
    InternalFacePolicy(const InternalFacePolicy&) = delete;
    InternalFacePolicy& operator=(const InternalFacePolicy&) = delete;
    void revoke() {
        std::lock_guard<std::mutex> guard(lock_);
        clear();
    }

    Decision observe(const WorkerObservation& evidence,
                     const facekids_guard::Snapshot& os_snapshot,
                     const std::wstring& expected_sid,
                     facekids_quota::Store& quota,
                     const char* trusted_day, ULONGLONG now_ms) {
        std::lock_guard<std::mutex> guard(lock_);
        // Unknown or switched faces cancel all prior candidates.
        clear();
        if (evidence.origin != EvidenceOrigin::ProtectedWorker)
            return Decision::DeniedUntrustedOrigin;
        if (now_ms < evidence.captured_tick_ms ||
            now_ms - evidence.captured_tick_ms > 3000)
            return Decision::DeniedStaleCapture;
        if (!valid_observation(evidence, now_ms))
            return Decision::DeniedCameraOrFace;
        if (evidence.session_id != os_snapshot.requested_id ||
            facekids_gate::check(os_snapshot, expected_sid, quota,
                                 evidence.child_id, trusted_day) !=
                facekids_gate::GatePrerequisite::ReadyForFacialPolicy)
            return Decision::DeniedNoQuotaOrSession;
        pending_child_ = evidence.child_id;
        pending_session_ = evidence.session_id;
        issued_at_ = now_ms;
        return Decision::PendingInternalRecheck;
    }

    Decision consume_pending(const facekids_guard::Snapshot& current_snapshot,
                             const std::wstring& expected_sid,
                             facekids_quota::Store& quota,
                             const char* trusted_day, ULONGLONG now_ms) {
        std::lock_guard<std::mutex> guard(lock_);
        const int child = pending_child_;
        const DWORD session = pending_session_;
        const ULONGLONG created = issued_at_;
        clear(); // always one-use, including denial on error
        if (child == 0) return Decision::DeniedNoPending;
        if (now_ms < created || now_ms - created > 8000 ||
            current_snapshot.requested_id != session ||
            current_snapshot.actual_id != session)
            return Decision::DeniedExpiredOrWrongSession;
        if (facekids_gate::check(current_snapshot, expected_sid, quota,
                                 child, trusted_day) !=
            facekids_gate::GatePrerequisite::ReadyForFacialPolicy)
            return Decision::DeniedNoQuotaOrSession;
        return Decision::ReadyForAdditionalControls;
    }
};

inline bool self_test(facekids_quota::Store& quota) {
    constexpr auto Locked = facekids_wts::LockView::Locked;
    const std::wstring child_sid = L"S-1-5-21-100-200-300-1005";
    const std::wstring parent_sid = L"S-1-5-21-100-200-300-1001";
    const char* day = "2026-10-20";
    facekids_guard::Snapshot os = {7, 7, Locked, child_sid, true};
    WorkerObservation face = {1, 7, 1, 3, true, true,
                              EvidenceOrigin::ProtectedWorker, 1000};
    InternalFacePolicy policy;
    auto arm = [&](ULONGLONG now = 1100) {
        return policy.observe(face, os, child_sid, quota, day, now);
    };
    auto redeem = [&](ULONGLONG now = 1200) {
        return policy.consume_pending(os, child_sid, quota, day, now);
    };
    if (arm()!=Decision::PendingInternalRecheck ||
        redeem()!=Decision::ReadyForAdditionalControls ||
        redeem()!=Decision::DeniedNoPending) return false;

    face.origin=EvidenceOrigin::Unknown;
    if (arm()!=Decision::DeniedUntrustedOrigin) return false;
    face.origin=EvidenceOrigin::ProtectedWorker;
    face.liveness_passed=false;
    if (arm()!=Decision::DeniedCameraOrFace) return false;
    face.liveness_passed=true;
    face.faces=2;
    if (arm()!=Decision::DeniedCameraOrFace) return false;
    face.faces=1;
    face.confirmations=2;
    if (arm()!=Decision::DeniedCameraOrFace) return false;
    face.confirmations=3;
    face.camera_healthy=false;
    if (arm()!=Decision::DeniedCameraOrFace) return false;
    face.camera_healthy=true;
    face.child_id=0;
    if (arm()!=Decision::DeniedCameraOrFace) return false;
    face.child_id=1;
    if (arm(5000)!=Decision::DeniedStaleCapture) return false;
    face.captured_tick_ms=1500;
    if (arm(1100)!=Decision::DeniedStaleCapture) return false;
    face.captured_tick_ms=1000;
    os.token_sid=parent_sid;
    if (arm()!=Decision::DeniedNoQuotaOrSession) return false;
    os.token_sid=child_sid;
    os.state=facekids_wts::LockView::Unlocked;
    if (arm()!=Decision::DeniedNoQuotaOrSession) return false;
    os.state=Locked;

    if (arm()!=Decision::PendingInternalRecheck) return false;
    if (redeem(9101)!=Decision::DeniedExpiredOrWrongSession ||
        redeem()!=Decision::DeniedNoPending) return false;
    if (arm()!=Decision::PendingInternalRecheck) return false;
    os.actual_id=8;
    if (redeem()!=Decision::DeniedExpiredOrWrongSession) return false;
    os.actual_id=7;
    if (arm()!=Decision::PendingInternalRecheck) return false;
    policy.revoke();
    if (redeem()!=Decision::DeniedNoPending) return false;

    // Failure/sibling switching never charges or authorizes the wrong child.
    if (!quota.charge(1,day,7200)) return false;
    if (arm()!=Decision::DeniedNoQuotaOrSession) return false;
    face.child_id=2;
    if (arm()!=Decision::PendingInternalRecheck) return false;
    if (!quota.charge(2,day,7200)) return false;
    if (redeem()!=Decision::DeniedNoQuotaOrSession) return false;
    face.child_id=3;
    if (arm()!=Decision::PendingInternalRecheck ||
        redeem()!=Decision::ReadyForAdditionalControls) return false;
    if (arm()!=Decision::PendingInternalRecheck) return false;
    face.origin=EvidenceOrigin::Unknown;
    if (arm()!=Decision::DeniedUntrustedOrigin ||
        redeem()!=Decision::DeniedNoPending) return false;
    return true;
}

} // namespace facekids_face
