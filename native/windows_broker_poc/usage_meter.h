// P0-42: simulated post-login elapsed-time accounting against WinSQLite.
// CANNOT unlock Windows, identify children or force the Windows lock screen.
// Not callable over any IPC; no live credential/camera evidence is available.
// The normal constructor deliberately disables synthetic accounting.
#pragma once
#include "quota_store.h"
#include "session_guard.h"
#include <windows.h>
#include <cstdint>
#include <mutex>
#include <string>

namespace facekids_usage {

enum class Result {
    Denied,
    ArmedForSyntheticTest,
    NoFullSecond,
    Charged,
    QuotaExhausted,
    PausedUnverifiedSession,
    PausedDayChanged,
    PausedClockRegression
};

inline bool valid_unlocked_wts(const facekids_guard::Snapshot& wts,
                               const std::wstring& expected_sid) {
    return wts.requested_id!=0 &&
           wts.requested_id!=0xffffffff &&
           wts.requested_id==wts.actual_id &&
           wts.state==facekids_wts::LockView::Unlocked &&
           wts.token_from_os &&
           facekids_guard::valid_local_account_sid(expected_sid) &&
           facekids_guard::valid_local_account_sid(wts.token_sid) &&
           facekids_guard::sid_equals(wts.token_sid,expected_sid);
}

class Meter {
    std::mutex mutex_;
    bool synthetic_enabled_=false;
    int child_=0;
    DWORD session_=0;
    ULONGLONG last_tick_=0;
    std::string day_;
    friend bool self_test(facekids_quota::Store&);
    explicit Meter(bool allowSynthetic):synthetic_enabled_(allowSynthetic){}
    void reset() {
        child_=0;
        session_=0;
        last_tick_=0;
        day_.clear();
    }
public:
    Meter()=default; // always disabled in production
    Meter(const Meter&)=delete;
    Meter& operator=(const Meter&)=delete;

    Result start(const facekids_guard::Snapshot& os,
                 const std::wstring& sid,
                 facekids_quota::Store& quota,
                 int child, const char* service_day,
                 ULONGLONG service_tick) {
        std::lock_guard<std::mutex> guard(mutex_);
        reset();
        // Synthetic child attribution is NEVER trusted in production.
        if(!synthetic_enabled_ ||
           !valid_unlocked_wts(os,sid) ||
           child<1 || child>3 || !facekids_date::valid(service_day))
            return Result::Denied;
        sqlite3_int64 remaining=0;
        if(!quota.remaining(child,service_day,&remaining) || remaining<=0)
            return Result::Denied;
        child_=child;
        session_=os.actual_id;
        last_tick_=service_tick;
        day_=service_day;
        return Result::ArmedForSyntheticTest;
    }

    Result pulse(const facekids_guard::Snapshot& os,
                 const std::wstring& sid,
                 facekids_quota::Store& quota,
                 const char* service_day,
                 ULONGLONG service_tick) {
        std::lock_guard<std::mutex> guard(mutex_);
        if(!synthetic_enabled_ || child_==0) return Result::Denied;
        if(!valid_unlocked_wts(os,sid) || os.actual_id!=session_) {
            reset();
            return Result::PausedUnverifiedSession;
        }
        if(!facekids_date::valid(service_day)) {
            reset();
            return Result::Denied;
        }
        if(service_tick<last_tick_) {
            reset();
            return Result::PausedClockRegression;
        }
        if(day_!=service_day) {
            // Do not silently continue across daily boundary: requires
            // fresh OS and facial verification before charging new day.
            reset();
            return Result::PausedDayChanged;
        }
        const ULONGLONG elapsed=service_tick-last_tick_;
        if(elapsed<1000) return Result::NoFullSecond;
        sqlite3_int64 remaining=0;
        if(!quota.remaining(child_,service_day,&remaining)) {
            reset();
            return Result::Denied;
        }
        if(remaining<=0) {
            reset();
            return Result::QuotaExhausted;
        }
        // Even if the PC suspended for multiple hours, elapsed monotonic
        // time may not produce a negative balance or integer overflow.
        const ULONGLONG seconds=elapsed/1000;
        const int debit=static_cast<int>(
            seconds < static_cast<ULONGLONG>(remaining)
                ? seconds : static_cast<ULONGLONG>(remaining));
        if(debit<=0 || debit>86400 || !quota.charge(child_,service_day,debit)) {
            reset();
            return Result::Denied;
        }
        if(static_cast<sqlite3_int64>(debit)==remaining) {
            reset();
            return Result::QuotaExhausted;
        }
        last_tick_+=static_cast<ULONGLONG>(debit)*1000;
        return Result::Charged;
    }
    void stop() {
        std::lock_guard<std::mutex> guard(mutex_);
        reset();
    }
};

// No actual child identities or faces are used by this isolated self-test.
inline bool self_test(facekids_quota::Store& quota) {
    const std::wstring childSid=L"S-1-5-21-100-200-300-1005";
    const std::wstring wrongSid=L"S-1-5-21-100-200-300-1001";
    constexpr auto Unlocked=facekids_wts::LockView::Unlocked;
    facekids_guard::Snapshot os={7,7,Unlocked,childSid,true};
    const char* day="2026-10-20";
    Meter production;
    if(production.start(os,childSid,quota,1,day,1000)!=Result::Denied)
        return false;
    Meter meter(true);
    if(meter.start(os,childSid,quota,1,day,1000)!=
       Result::ArmedForSyntheticTest) return false;
    if(meter.pulse(os,childSid,quota,day,1800)!=Result::NoFullSecond)
        return false;
    if(meter.pulse(os,childSid,quota,day,2500)!=Result::Charged)
        return false;
    sqlite3_int64 remaining=0;
    if(!quota.remaining(1,day,&remaining) || remaining!=7199)
        return false;
    os.state=facekids_wts::LockView::Locked;
    if(meter.pulse(os,childSid,quota,day,4000)!=
       Result::PausedUnverifiedSession) return false;
    if(meter.pulse(os,childSid,quota,day,5000)!=Result::Denied)
        return false;
    os.state=Unlocked;
    if(meter.start(os,childSid,quota,2,day,10000)!=
       Result::ArmedForSyntheticTest) return false;
    os.token_sid=wrongSid;
    if(meter.pulse(os,childSid,quota,day,13000)!=
       Result::PausedUnverifiedSession) return false;
    os.token_sid=childSid;
    if(meter.start(os,childSid,quota,2,day,10000)!=
       Result::ArmedForSyntheticTest) return false;
    os.actual_id=8;
    if(meter.pulse(os,childSid,quota,day,13000)!=
       Result::PausedUnverifiedSession) return false;
    os.actual_id=7;
    if(meter.start(os,childSid,quota,3,day,10000)!=
       Result::ArmedForSyntheticTest) return false;
    if(meter.pulse(os,childSid,quota,day,9999)!=
       Result::PausedClockRegression) return false;
    if(meter.start(os,childSid,quota,3,day,10000)!=
       Result::ArmedForSyntheticTest) return false;
    if(meter.pulse(os,childSid,quota,"2026-10-21",11000)!=
       Result::PausedDayChanged) return false;
    if(meter.start(os,childSid,quota,3,day,10000)!=
       Result::ArmedForSyntheticTest) return false;
    // Long elapsed time exhausts the quota without overdrawing.
    if(meter.pulse(os,childSid,quota,day,10000+7200ull*1000ull)!=
       Result::QuotaExhausted) return false;
    if(!quota.remaining(3,day,&remaining) || remaining!=0) return false;
    if(meter.start(os,childSid,quota,3,day,12000)!=Result::Denied)
        return false;
    if(!quota.remaining(2,day,&remaining) || remaining!=7200) return false;
    return true;
}

} // namespace facekids_usage
