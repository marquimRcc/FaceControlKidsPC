// Validate actual calendar days before using them as quota ledger keys.
#pragma once
#include <cstring>
namespace facekids_date {
inline bool valid(const char* day) {
    if (!day || std::strlen(day)!=10) return false;
    for(int i=0;i<10;++i) {
        if(i==4 || i==7) {if(day[i]!='-') return false;}
        else if(day[i]<'0'||day[i]>'9') return false;
    }
    const int year=(day[0]-'0')*1000+(day[1]-'0')*100+(day[2]-'0')*10+day[3]-'0';
    const int month=(day[5]-'0')*10+day[6]-'0';
    const int date=(day[8]-'0')*10+day[9]-'0';
    if(year<2000||month<1||month>12||date<1) return false;
    const int days[]={31,28,31,30,31,30,31,31,30,31,30,31};
    const bool leap=year%4==0&&(year%100!=0||year%400==0);
    return date<=days[month-1]+(month==2&&leap?1:0);
}
inline bool self_test() {
    return valid("2026-10-20")&&valid("2028-02-29")&&
           !valid("2026-02-29")&&!valid("2026-02-30")&&
           !valid("2026-13-01")&&!valid("2026-00-01")&&
           !valid("2026-10-x0")&&!valid("2026-10-2")&&!valid(nullptr);
}
}
