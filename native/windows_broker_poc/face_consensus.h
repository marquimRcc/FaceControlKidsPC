// P0-46: temporal consistency of SFace *candidates*.
// This is NOT liveness, origin authentication, or Windows logon.
// A static photograph can satisfy consistency; production must still deny.
#pragma once
#include "face_matcher.h"
#include <windows.h>
#include <cstdint>

namespace facekids_consensus {
enum class State { Reset, Collecting, StableCandidateOnly };
class Window {
    DWORD session_=0;
    int child_=0;
    int count_=0;
    ULONGLONG first_=0, last_=0;
public:
    void revoke(){session_=0;child_=0;count_=0;first_=last_=0;}
    State observe(const facekids_matcher::Match& match, DWORD session,
                  ULONGLONG monotonic_ms, unsigned int face_count) {
        if(face_count!=1 || session==0 || session==0xffffffff ||
           match.status!=facekids_matcher::Status::CandidateOnly ||
           match.child_id<1 || match.child_id>3) {
            revoke();
            return State::Reset;
        }
        if(count_>0 && (child_!=match.child_id || session_!=session ||
                        monotonic_ms<last_ || monotonic_ms<first_ ||
                        monotonic_ms-first_>3000)) {
            revoke();
        }
        if(count_==0) {
            first_=monotonic_ms;
            child_=match.child_id;
            session_=session;
            count_=1;
        } else if(count_<3) {
            ++count_;
        } else {
            // Do not indefinitely reuse a completed candidate window.
            revoke();
            return State::Reset;
        }
        last_=monotonic_ms;
        return count_==3 ? State::StableCandidateOnly : State::Collecting;
    }
    // Consumer cannot convert candidate to login authorization.
    bool permits_logon() const { return false; }
};
inline bool self_test() {
    Window w;
    facekids_matcher::Match one={facekids_matcher::Status::CandidateOnly,1,0.99};
    facekids_matcher::Match two={facekids_matcher::Status::CandidateOnly,2,0.99};
    facekids_matcher::Match ambiguous={facekids_matcher::Status::Ambiguous,0,0.99};
    if(w.observe(one,7,1000,1)!=State::Collecting ||
       w.observe(one,7,1500,1)!=State::Collecting ||
       w.observe(one,7,1800,1)!=State::StableCandidateOnly ||
       w.permits_logon()) return false;
    if(w.observe(one,7,1801,1)!=State::Reset ||
       w.observe(one,7,2000,1)!=State::Collecting ||
       w.observe(two,7,2200,1)!=State::Collecting ||
       w.observe(two,7,2250,1)!=State::Collecting ||
       w.observe(two,7,2300,1)!=State::StableCandidateOnly) return false;
    w.revoke();
    if(w.observe(one,7,1000,1)!=State::Collecting ||
       w.observe(one,7,1100,2)!=State::Reset ||
       w.observe(one,7,1200,1)!=State::Collecting ||
       w.observe(ambiguous,7,1300,1)!=State::Reset ||
       w.observe(one,7,2000,1)!=State::Collecting ||
       w.observe(one,8,2200,1)!=State::Collecting ||
       w.observe(one,8,2100,1)!=State::Collecting) return false;
    w.revoke();
    if(w.observe(one,7,1000,1)!=State::Collecting ||
       w.observe(one,7,5000,1)!=State::Collecting ||
       w.observe(one,7,5500,1)!=State::Collecting ||
       w.observe(one,7,6000,1)!=State::StableCandidateOnly) return false;
    return true;
}
} // namespace facekids_consensus
