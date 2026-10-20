// P0-49: per-session one-use *internal prerequisite* only.
// Does not contain Windows credentials, CP tokens or a logon grant.
// Runtime remains disabled until a trusted camera/liveness worker exists.
#pragma once
#include "face_quota_bridge.h"
#include <mutex>
#include <type_traits>

namespace facekids_ticket {
enum class Result {
    Denied, ArmedSyntheticOnly, ReadyForFurtherVerification,
    ExpiredOrMismatched, ConsumedOrMissing, QuotaOrSessionDenied
};

class OneUse {
    mutable std::mutex mutex_;
    bool synthetic_=false;
    int child_=0;
    DWORD session_=0;
    ULONGLONG created_=0;
    friend bool self_test(facekids_quota::Store&);
    explicit OneUse(bool synthetic):synthetic_(synthetic){}
    void reset(){child_=0;session_=0;created_=0;}
public:
    OneUse()=default;
    OneUse(const OneUse&)=delete;
    OneUse& operator=(const OneUse&)=delete;
    Result arm(const facekids_bridge::Assessment& assessment,
               const facekids_guard::Snapshot& locked_session,
               ULONGLONG monotonic_ms) {
        std::lock_guard<std::mutex> guard(mutex_);
        reset();
        if(!synthetic_ ||
           assessment.verdict!=facekids_bridge::Verdict::NeedsTrustedCameraAndLiveness ||
           assessment.child<1||assessment.child>3 ||
           locked_session.requested_id==0 ||
           locked_session.requested_id!=locked_session.actual_id ||
           locked_session.state!=facekids_wts::LockView::Locked)
            return Result::Denied;
        child_=assessment.child;
        session_=locked_session.actual_id;
        created_=monotonic_ms;
        return Result::ArmedSyntheticOnly;
    }
    Result use(const facekids_guard::Snapshot& current,
               const std::wstring& expected_sid,
               facekids_quota::Store& db,
               const char* trusted_day, ULONGLONG monotonic_ms) {
        std::lock_guard<std::mutex> guard(mutex_);
        int child=child_;
        DWORD session=session_;
        ULONGLONG created=created_;
        reset(); // ALWAYS consume, including all errors and denial
        if(!synthetic_ || child==0) return Result::ConsumedOrMissing;
        if(monotonic_ms<created || monotonic_ms-created>8000 ||
           current.requested_id!=session || current.actual_id!=session)
           return Result::ExpiredOrMismatched;
        if(facekids_gate::check(current,expected_sid,db,child,trusted_day)!=
           facekids_gate::GatePrerequisite::ReadyForFacialPolicy)
           return Result::QuotaOrSessionDenied;
        return Result::ReadyForFurtherVerification;
    }
    // No state returned above is a Windows logon credential.
    bool permits_windows_logon() const {return false;}
};
static_assert(!std::is_constructible_v<OneUse,bool>,
              "Synthetic ticket must not be constructible from production code");

inline bool self_test(facekids_quota::Store& db) {
    const std::wstring sid=L"S-1-5-21-100-200-300-1005";
    const char* day="2026-10-20";
    facekids_guard::Snapshot os={7,7,facekids_wts::LockView::Locked,sid,true};
    std::array<float,128> a={};
    a[0]=1;
    if(!db.add_template(1,a))return false;
    const auto assessment=facekids_bridge::assess(db,a,os,sid,day);
    if(assessment.verdict!=facekids_bridge::Verdict::NeedsTrustedCameraAndLiveness)
        return false;
    OneUse production;
    if(production.arm(assessment,os,1000)!=Result::Denied ||
       production.permits_windows_logon()) return false;
    OneUse synthetic(true);
    if(synthetic.arm(assessment,os,1000)!=Result::ArmedSyntheticOnly ||
       synthetic.use(os,sid,db,day,1200)!=Result::ReadyForFurtherVerification ||
       synthetic.use(os,sid,db,day,1201)!=Result::ConsumedOrMissing)
        return false;
    if(synthetic.arm(assessment,os,1000)!=Result::ArmedSyntheticOnly ||
       synthetic.use(os,sid,db,day,9002)!=Result::ExpiredOrMismatched)
        return false;
    if(synthetic.arm(assessment,os,1000)!=Result::ArmedSyntheticOnly)
        return false;
    os.actual_id=8;
    if(synthetic.use(os,sid,db,day,1500)!=Result::ExpiredOrMismatched)
        return false;
    os.actual_id=7;
    if(synthetic.arm(assessment,os,1000)!=Result::ArmedSyntheticOnly)
        return false;
    if(!db.charge(1,day,7200)) return false;
    if(synthetic.use(os,sid,db,day,1500)!=Result::QuotaOrSessionDenied)
        return false;
    if(synthetic.arm(assessment,os,1000)!=Result::ArmedSyntheticOnly)
        return false;
    os.token_sid=L"S-1-5-21-100-200-300-1001";
    if(synthetic.use(os,sid,db,day,1500)!=Result::QuotaOrSessionDenied)
        return false;
    return true;
}

} // namespace facekids_ticket
