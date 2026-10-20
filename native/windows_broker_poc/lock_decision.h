// P0-51: decide whether child-session quota exhaustion would require
// a Windows lock. NO Win32 lock/disconnect call is issued anywhere here.
// This can be tested safely on CI. A real per-session enforcement
// mechanism needs a privileged, VM-validated implementation later.
#pragma once
#include "usage_meter.h"
namespace facekids_lock_policy {
enum class Action { NoAction, CandidateLockChildOnly };
inline Action evaluate(facekids_usage::Result meter_event,
                       const facekids_guard::Snapshot& current_session,
                       const std::wstring& child_account_sid,
                       bool verified_child_binding) {
    // Until a trustworthy camera and per-child binding exist, production
    // must not claim ownership of another person's Windows session.
    if(!verified_child_binding ||
       meter_event!=facekids_usage::Result::QuotaExhausted ||
       !facekids_usage::valid_unlocked_wts(current_session,child_account_sid))
        return Action::NoAction;
    return Action::CandidateLockChildOnly;
}
inline bool self_test() {
    const std::wstring child=L"S-1-5-21-100-200-300-1005";
    const std::wstring admin=L"S-1-5-21-100-200-300-1001";
    facekids_guard::Snapshot os={7,7,facekids_wts::LockView::Unlocked,child,true};
    if(evaluate(facekids_usage::Result::QuotaExhausted,os,child,false)!=Action::NoAction)
        return false;
    if(evaluate(facekids_usage::Result::Charged,os,child,true)!=Action::NoAction)
        return false;
    if(evaluate(facekids_usage::Result::QuotaExhausted,os,child,true)!=
       Action::CandidateLockChildOnly) return false;
    os.token_sid=admin;
    if(evaluate(facekids_usage::Result::QuotaExhausted,os,child,true)!=Action::NoAction)
        return false;
    os.token_sid=child;
    os.state=facekids_wts::LockView::Locked;
    if(evaluate(facekids_usage::Result::QuotaExhausted,os,child,true)!=Action::NoAction)
        return false;
    os.state=facekids_wts::LockView::Unlocked;
    os.actual_id=8;
    if(evaluate(facekids_usage::Result::QuotaExhausted,os,child,true)!=Action::NoAction)
        return false;
    os.actual_id=7;
    os.token_from_os=false;
    if(evaluate(facekids_usage::Result::QuotaExhausted,os,child,true)!=Action::NoAction)
        return false;
    return true;
}
} // namespace facekids_lock_policy
