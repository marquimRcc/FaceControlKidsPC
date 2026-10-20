// P0-48 software integration: FACE CANDIDATE + WTS + protected quota.
// An identity candidate is NOT authenticated and never grants logon.
// This code cannot be invoked over the user-visible diagnostic pipe.
#pragma once
#include "face_matcher.h"
#include "quota_gate.h"

namespace facekids_bridge {
enum class Verdict {
    Unrecognized, Ambiguous, InvalidProbe, StorageError,
    SessionDenied, BalanceUnavailable, QuotaExhausted,
    NeedsTrustedCameraAndLiveness // not permission to log on
};
struct Assessment {
    Verdict verdict=Verdict::Unrecognized;
    int child=0;
    bool permits_unlock() const { return false; }
    bool starts_meter() const { return false; }
};
inline Assessment assess(facekids_quota::Store& database,
                         const std::array<float,128>& probe,
                         const facekids_guard::Snapshot& os,
                         const std::wstring& expected_sid,
                         const char* trusted_day) {
    const auto match=facekids_matcher::candidate(database,probe);
    switch(match.status) {
        case facekids_matcher::Status::InvalidProbe: return {Verdict::InvalidProbe,0};
        case facekids_matcher::Status::StorageError: return {Verdict::StorageError,0};
        case facekids_matcher::Status::Ambiguous: return {Verdict::Ambiguous,0};
        case facekids_matcher::Status::Unknown: return {Verdict::Unrecognized,0};
        case facekids_matcher::Status::CandidateOnly: break;
    }
    if(match.child_id<1 || match.child_id>3) return {Verdict::Unrecognized,0};
    auto gate=facekids_gate::check(os,expected_sid,database,match.child_id,trusted_day);
    switch(gate) {
        case facekids_gate::GatePrerequisite::ReadyForFacialPolicy:
            return {Verdict::NeedsTrustedCameraAndLiveness,match.child_id};
        case facekids_gate::GatePrerequisite::SessionDenied:
            return {Verdict::SessionDenied,0};
        case facekids_gate::GatePrerequisite::QuotaUnavailable:
            return {Verdict::BalanceUnavailable,0};
        case facekids_gate::GatePrerequisite::QuotaExhausted:
            return {Verdict::QuotaExhausted,0};
    }
    return {Verdict::StorageError,0};
}
inline bool self_test(facekids_quota::Store& db) {
    const std::wstring sid=L"S-1-5-21-100-200-300-1005";
    facekids_guard::Snapshot os={7,7,facekids_wts::LockView::Locked,sid,true};
    const char* date="2026-10-20";
    std::array<float,128> a={},b={},unknown={},spoof={};
    a[0]=1; b[1]=1; unknown[2]=1;
    spoof[0]=std::numeric_limits<float>::quiet_NaN();
    if(!db.add_template(1,a) || !db.add_template(2,b)) return false;
    auto first=assess(db,a,os,sid,date);
    if(first.verdict!=Verdict::NeedsTrustedCameraAndLiveness || first.child!=1 ||
       first.permits_unlock() || first.starts_meter()) return false;
    if(assess(db,unknown,os,sid,date).verdict!=Verdict::Unrecognized ||
       assess(db,spoof,os,sid,date).verdict!=Verdict::InvalidProbe)
        return false;
    os.state=facekids_wts::LockView::Unlocked;
    if(assess(db,a,os,sid,date).verdict!=Verdict::SessionDenied)
        return false;
    os.state=facekids_wts::LockView::Locked;
    if(!db.charge(1,date,7200)) return false;
    if(assess(db,a,os,sid,date).verdict!=Verdict::QuotaExhausted) return false;
    auto second=assess(db,b,os,sid,date);
    if(second.verdict!=Verdict::NeedsTrustedCameraAndLiveness ||
       second.child!=2 || second.starts_meter()) return false;
    if(assess(db,a,os,sid,"2026-02-30").verdict!=Verdict::BalanceUnavailable)
        return false;
    if(!db.add_template(3,b)) return false;
    if(assess(db,b,os,sid,date).verdict!=Verdict::Ambiguous) return false;
    return true;
}
} // namespace facekids_bridge
