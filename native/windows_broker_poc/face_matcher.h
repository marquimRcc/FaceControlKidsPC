// P0-45/46: SFace 128-float matcher inside the protected broker.
// It does NOT read a camera or attest liveness. Its identity is only a
// synthetic/algorithmic candidate, never permission to unlock Windows.
#pragma once
#include "quota_store.h"
#include <array>
#include <cmath>
#include <limits>
#include <algorithm>

namespace facekids_matcher {
enum class Status { CandidateOnly, Unknown, Ambiguous, InvalidProbe, StorageError };
struct Match {
    Status status=Status::Unknown;
    int child_id=0;
    double score=0;
    bool authenticates_windows() const {return false;}
};

inline bool normalized_dot(const std::array<float,128>& a,
                           const std::array<float,128>& b,
                           double* similarity) {
    double aa=0,bb=0,ab=0;
    for(size_t i=0;i<128;++i) {
        if(!std::isfinite(a[i])||!std::isfinite(b[i])) return false;
        const double x=a[i],y=b[i];
        aa+=x*x; bb+=y*y; ab+=x*y;
    }
    if(!std::isfinite(aa)||!std::isfinite(bb)||!std::isfinite(ab) ||
       aa<=1e-12||bb<=1e-12) return false;
    *similarity=std::max(-1.0,std::min(1.0,ab/(std::sqrt(aa)*std::sqrt(bb))));
    return std::isfinite(*similarity);
}

// Compare by PERSON (max similarity over enrollment samples), then require
// a confidence threshold and a separation margin from the runner-up PERSON.
// Raw cosine score alone cannot verify presentation authenticity.
inline Match candidate(facekids_quota::Store& db,
                       const std::array<float,128>& observed,
                       double threshold=0.50, double min_margin=0.07) {
    Match result;
    if(!std::isfinite(threshold)||!std::isfinite(min_margin) ||
       threshold<0||threshold>1||min_margin<0||min_margin>1) {
        result.status=Status::InvalidProbe; return result;
    }
    double magnitude=0;
    for(float v:observed) {
        if(!std::isfinite(v)) {result.status=Status::InvalidProbe; return result;}
        magnitude+=double(v)*double(v);
    }
    if(!std::isfinite(magnitude)||magnitude<=1e-12) {
        result.status=Status::InvalidProbe; return result;
    }
    double top=-2,runner=-2;
    int winner=0;
    for(int child=1;child<=3;++child) {
        std::vector<std::array<float,128>> vectors;
        if(!db.read_templates(child,&vectors)) {
            return {Status::StorageError,0,0};
        }
        double best=-2;
        for(const auto& reference:vectors) {
            double cosine=0;
            if(!normalized_dot(observed,reference,&cosine))
                return {Status::StorageError,0,0};
            best=std::max(best,cosine);
        }
        if(best>top) {
            runner=top;
            top=best;
            winner=child;
        } else if(best>runner) runner=best;
    }
    if(!winner || top<threshold) return {Status::Unknown,0,std::max(0.0,top)};
    if(runner>-2 && top-runner<min_margin) return {Status::Ambiguous,0,top};
    return {Status::CandidateOnly,winner,top};
}

inline bool self_test(facekids_quota::Store& db) {
    std::array<float,128> a={},b={},x={},unknown={},bad={};
    a[0]=1; b[1]=1; x[0]=1; x[1]=1; unknown[2]=1;
    bad[0]=std::numeric_limits<float>::quiet_NaN();
    if(!db.add_template(1,a) || !db.add_template(2,b)) return false;
    auto first=candidate(db,a);
    if(first.status!=Status::CandidateOnly||first.child_id!=1 ||
       first.authenticates_windows()) return false;
    if(candidate(db,b).child_id!=2 ||
       candidate(db,unknown).status!=Status::Unknown ||
       candidate(db,bad).status!=Status::InvalidProbe ||
       candidate(db,std::array<float,128>{}).status!=Status::InvalidProbe)
       return false;
    if(!db.add_template(3,a)) return false;
    if(candidate(db,a).status!=Status::Ambiguous) return false;
    int erased=0;
    if(!db.erase_templates(3,&erased)||erased!=1) return false;
    const auto after=candidate(db,a);
    if(after.status!=Status::CandidateOnly||after.child_id!=1) return false;
    if(candidate(db,x).status!=Status::Unknown) return false;
    return true;
}
} // namespace facekids_matcher
