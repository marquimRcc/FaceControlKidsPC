// P0-51: dry-run child-only quota exhaustion policy.
// NEVER issues LockWorkStation, WTSDisconnectSession or credentials.
// Runtime is disabled until a signed session/identity binding exists.
#pragma once
#include "usage_meter.h"
#include <type_traits>
namespace facekids_lock_policy {
enum class Action { NoAction, CandidateLockChildOnly }; // candidate != action
class Policy {
    bool synthetic_allowed_=false;
    explicit Policy(bool synthetic):synthetic_allowed_(synthetic){}
    friend bool self_test();
public:
    Policy()=default;
    Policy(const Policy&)=delete;
    Policy& operator=(const Policy&)=delete;
    Action evaluate(facekids_usage::Result event,
                    const facekids_guard::Snapshot& current_session,
                    const std::wstring& child_account_sid) const {
        // No external caller can set a boolean flag to enable real locking.
        if(!synthetic_allowed_ ||
           event!=facekids_usage::Result::QuotaExhausted ||
           !facekids_usage::valid_unlocked_wts(current_session,child_account_sid))
            return Action::NoAction;
        return Action::CandidateLockChildOnly;
    }
};
static_assert(!std::is_constructible_v<Policy,bool>,
              "Synthetic lock decision must remain unavailable outside self-test");
inline bool self_test() {
    const std::wstring child=L"S-1-5-21-100-200-300-1005";
    const std::wstring admin=L"S-1-5-21-100-200-300-1001";
    facekids_guard::Snapshot os={7,7,facekids_wts::LockView::Unlocked,child,true};
    Policy production;
    if(production.evaluate(facekids_usage::Result::QuotaExhausted,os,child)!=
       Action::NoAction) return false;
    Policy synthetic(true);
    if(synthetic.evaluate(facekids_usage::Result::Charged,os,child)!=
       Action::NoAction) return false;
    if(synthetic.evaluate(facekids_usage::Result::QuotaExhausted,os,child)!=
       Action::CandidateLockChildOnly) return false;
    os.token_sid=admin;
    if(synthetic.evaluate(facekids_usage::Result::QuotaExhausted,os,child)!=
       Action::NoAction) return false;
    os.token_sid=child;
    os.state=facekids_wts::LockView::Locked;
    if(synthetic.evaluate(facekids_usage::Result::QuotaExhausted,os,child)!=
       Action::NoAction) return false;
    os.state=facekids_wts::LockView::Unlocked;
    os.actual_id=8;
    if(synthetic.evaluate(facekids_usage::Result::QuotaExhausted,os,child)!=
       Action::NoAction) return false;
    os.actual_id=7;
    os.token_from_os=false;
    if(synthetic.evaluate(facekids_usage::Result::QuotaExhausted,os,child)!=
       Action::NoAction) return false;
    return true;
}
} // namespace facekids_lock_policy
