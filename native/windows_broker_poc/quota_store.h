// P0-8 Windows broker quota storage. NOT an IPC endpoint or login unlocker.
// Uses Microsoft-maintained WinSQLite (Windows 10/11) in ProgramData under
// an explicit DACL containing ONLY LocalSystem and Administrators.
// No biometric templates, password material or user-controlled filesystem paths.
#pragma once
#include <windows.h>
#include <aclapi.h>
#include <sddl.h>
#include <winsqlite/winsqlite3.h>
#include "date_validation.h"
#include <shlobj.h>
#include <string>
#include <cstdint>
#include <cstdio>
#include <cwchar>
#include <cstring>
#include <array>
#include <cmath>
#include <limits>

#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "winsqlite3.lib")

namespace facekids_quota {

static constexpr wchar_t kSecureDirectoryDacl[] =
    L"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)";

inline bool allowed_acl(const std::wstring& path, bool requireProtected) {
    if (path.empty()) return false;
    const DWORD attrs = GetFileAttributesW(path.c_str());
    if (attrs == INVALID_FILE_ATTRIBUTES || (attrs & FILE_ATTRIBUTE_REPARSE_POINT))
        return false; // prohibit junctions/symlinks in the trusted data path
    PACL acl = nullptr;
    PSID owner = nullptr;
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    DWORD err = GetNamedSecurityInfoW(
        const_cast<LPWSTR>(path.c_str()), SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION | OWNER_SECURITY_INFORMATION,
        &owner, nullptr, &acl, nullptr, &descriptor);
    if (err != ERROR_SUCCESS || !descriptor) return false;
    BOOL present = FALSE, defaulted = FALSE;
    PACL current = nullptr;
    SECURITY_DESCRIPTOR_CONTROL control = 0;
    DWORD revision = 0;
    bool valid = GetSecurityDescriptorDacl(descriptor, &present, &current, &defaulted)
        && present && current && acl == current
        && GetSecurityDescriptorControl(descriptor, &control, &revision)
        && (!requireProtected || (control & SE_DACL_PROTECTED));
    BYTE sys[SECURITY_MAX_SID_SIZE] = {}, adm[SECURITY_MAX_SID_SIZE] = {};
    DWORD sysBytes = sizeof(sys), admBytes = sizeof(adm);
    valid = valid && CreateWellKnownSid(WinLocalSystemSid, nullptr, sys, &sysBytes)
        && CreateWellKnownSid(WinBuiltinAdministratorsSid, nullptr, adm, &admBytes);
    // A child may create a folder with a seemingly safe DACL while
    // retaining its OWNER privilege to rewrite that DACL later.
    // Only SYSTEM or builtin Administrators may own protected storage.
    valid = valid && owner && IsValidSid(owner) &&
        (EqualSid(owner,sys) || EqualSid(owner,adm));
    bool systemFound = false, adminsFound = false;
    if (valid) {
        ACL_SIZE_INFORMATION info = {};
        valid = GetAclInformation(acl, &info, sizeof(info), AclSizeInformation) != FALSE
            && info.AceCount == 2;
        for (DWORD i = 0; valid && i < info.AceCount; ++i) {
            void* raw = nullptr;
            if (!GetAce(acl, i, &raw)) { valid = false; break; }
            auto* ace = static_cast<ACE_HEADER*>(raw);
            if (ace->AceType != ACCESS_ALLOWED_ACE_TYPE) {
                // No foreign deny/allow or callback/conditional ACEs accepted.
                valid = false; break;
            }
            auto* allow = static_cast<ACCESS_ALLOWED_ACE*>(raw);
            PSID who = &allow->SidStart;
            // Reject read-only masks and duplicate ACEs for trusted SIDs.
            if ((allow->Mask & FILE_ALL_ACCESS) != FILE_ALL_ACCESS) {
                valid=false;
            } else if (EqualSid(who, sys)) {
                if (systemFound) valid=false;
                systemFound = true;
            } else if (EqualSid(who, adm)) {
                if (adminsFound) valid=false;
                adminsFound = true;
            } else {
                valid=false;
            }
        }
    }
    LocalFree(descriptor);
    return valid && systemFound && adminsFound;
}

inline bool make_secure_directory(const std::wstring& root) {
    if (root.empty()) return false;
    const DWORD attrs = GetFileAttributesW(root.c_str());
    if (attrs != INVALID_FILE_ATTRIBUTES) {
        return (attrs & FILE_ATTRIBUTE_DIRECTORY) != 0 && allowed_acl(root, true);
    }
    if (GetLastError() != ERROR_FILE_NOT_FOUND &&
        GetLastError() != ERROR_PATH_NOT_FOUND) return false;
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
            kSecureDirectoryDacl, SDDL_REVISION_1, &descriptor, nullptr))
        return false;
    SECURITY_ATTRIBUTES attributes = {sizeof(attributes), descriptor, FALSE};
    BOOL created = CreateDirectoryW(root.c_str(), &attributes);
    LocalFree(descriptor);
    return created && allowed_acl(root, true);
}

inline bool exec(sqlite3* db, const char* sql) {
    return db && sqlite3_exec(db, sql, nullptr, nullptr, nullptr) == SQLITE_OK;
}

// A successful SQLite API call is not proof of a healthy ledger.
// Check the actual quick_check result; any error must block service startup.
inline bool healthy_database(sqlite3* db) {
    sqlite3_stmt* check=nullptr;
    if (!db || sqlite3_prepare_v2(db, "PRAGMA quick_check(1);", -1,
                                  &check, nullptr) != SQLITE_OK)
        return false;
    bool healthy=false;
    if (sqlite3_step(check)==SQLITE_ROW) {
        const unsigned char* value=sqlite3_column_text(check, 0);
        healthy=value && std::strcmp(reinterpret_cast<const char*>(value), "ok")==0;
    }
    sqlite3_finalize(check);
    return healthy;
}

class Store {
    sqlite3* db_ = nullptr;
    std::wstring root_;
    static bool statement_int(sqlite3* db, const char* sql,
                              int child, const char* day, sqlite3_int64* result) {
        sqlite3_stmt* stmt = nullptr;
        if (!db || sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) != SQLITE_OK)
            return false;
        bool success = sqlite3_bind_int(stmt, 1, child) == SQLITE_OK
            && sqlite3_bind_text(stmt, 2, day, -1, SQLITE_TRANSIENT) == SQLITE_OK
            && sqlite3_step(stmt) == SQLITE_ROW;
        if (success) *result = sqlite3_column_int64(stmt, 0);
        sqlite3_finalize(stmt);
        return success;
    }
public:
    Store() = default;
    Store(const Store&) = delete;
    Store& operator=(const Store&) = delete;
    ~Store() { close(); }
    void close() {
        if (db_) sqlite3_close(db_);
        db_ = nullptr;
    }
    bool open(const std::wstring& root) {
        close();
        if (!make_secure_directory(root)) return false;
        root_ = root;
        const std::wstring file = root + L"\\quota.sqlite3";
        DWORD attrs = GetFileAttributesW(file.c_str());
        if (attrs != INVALID_FILE_ATTRIBUTES && !allowed_acl(file, false))
            return false;
        if (sqlite3_open16(file.c_str(), &db_) != SQLITE_OK) {
            close(); return false;
        }
        // Secure directory guarantees newly created DB/journal inheritance.
        if (!allowed_acl(file, false) ||
            !healthy_database(db_) ||
            !exec(db_, "PRAGMA journal_mode=DELETE;") ||
            !exec(db_, "PRAGMA foreign_keys=ON;") ||
            !exec(db_, "PRAGMA secure_delete=ON;") ||
            !exec(db_, "PRAGMA busy_timeout=5000;") ||
            !exec(db_, "CREATE TABLE IF NOT EXISTS children("
                       "id INTEGER PRIMARY KEY CHECK(id BETWEEN 1 AND 3),"
                       "limit_seconds INTEGER NOT NULL CHECK(limit_seconds BETWEEN 60 AND 86400));") ||
            !exec(db_, "CREATE TABLE IF NOT EXISTS daily_quota("
                       "child_id INTEGER NOT NULL REFERENCES children(id),"
                       "day TEXT NOT NULL,"
                       "used_seconds INTEGER NOT NULL DEFAULT 0 CHECK(used_seconds>=0),"
                       "bonus_seconds INTEGER NOT NULL DEFAULT 0 CHECK(bonus_seconds>=0),"
                       "PRIMARY KEY(child_id,day));") ||
            !exec(db_, "CREATE TABLE IF NOT EXISTS face_templates("
                       "template_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                       "child_id INTEGER NOT NULL REFERENCES children(id),"
                       "embedding BLOB NOT NULL CHECK(length(embedding)=512));") ||
            !exec(db_, "INSERT OR IGNORE INTO children(id,limit_seconds) VALUES"
                       "(1,7200),(2,7200),(3,7200);")) {
            close(); return false;
        }
        return true;
    }
    // P0-36: protected enrollment ledger. No caller-controlled IPC or
    // Windows login uses this in the current proof of concept.
    // Synthetic data tests ONLY; future APIs need verified parent identity.
    bool add_template(int child, const std::array<float,128>& vector) {
        if (!db_ || child<1 || child>3) return false;
        double sum=0.0;
        for(float value: vector) {
            if(!std::isfinite(value)) return false;
            sum+=double(value)*double(value);
        }
        if (!std::isfinite(sum) || sum<=1.0e-12) return false;
        if (!exec(db_, "BEGIN IMMEDIATE;")) return false;
        sqlite3_stmt* stmt=nullptr;
        bool ok=false;
        do {
            if(sqlite3_prepare_v2(db_,
               "INSERT INTO face_templates(child_id,embedding)"
               " SELECT ?1,?2 WHERE"
               " (SELECT COUNT(*) FROM face_templates WHERE child_id=?1)<5;",
               -1, &stmt, nullptr)!=SQLITE_OK) break;
            if(sqlite3_bind_int(stmt,1,child)!=SQLITE_OK ||
               sqlite3_bind_blob(stmt,2,vector.data(),
                                 static_cast<int>(sizeof(float)*vector.size()),
                                 SQLITE_TRANSIENT)!=SQLITE_OK ||
               sqlite3_step(stmt)!=SQLITE_DONE ||
               sqlite3_changes(db_)!=1) break;
            ok=true;
        } while(false);
        if(stmt) sqlite3_finalize(stmt);
        if(ok) ok=exec(db_, "COMMIT;");
        if(!ok) exec(db_, "ROLLBACK;");
        return ok;
    }

    bool count_templates(int child, int* number) const {
        if(!db_ || child<1 || child>3 || !number) return false;
        sqlite3_stmt* statement=nullptr;
        if(sqlite3_prepare_v2(db_,
           "SELECT COUNT(*) FROM face_templates WHERE child_id=?1;",
           -1,&statement,nullptr)!=SQLITE_OK) return false;
        bool ok=sqlite3_bind_int(statement,1,child)==SQLITE_OK &&
                sqlite3_step(statement)==SQLITE_ROW;
        if(ok) *number=sqlite3_column_int(statement,0);
        sqlite3_finalize(statement);
        return ok;
    }

    bool erase_templates(int child, int* erased) {
        if(!db_ || child<1 || child>3 || !erased) return false;
        sqlite3_stmt* statement=nullptr;
        if(sqlite3_prepare_v2(db_,
           "DELETE FROM face_templates WHERE child_id=?1;",
           -1,&statement,nullptr)!=SQLITE_OK) return false;
        bool ok=sqlite3_bind_int(statement,1,child)==SQLITE_OK &&
                sqlite3_step(statement)==SQLITE_DONE;
        if(ok) *erased=sqlite3_changes(db_);
        sqlite3_finalize(statement);
        return ok;
    }

    bool remaining(int child, const char* day, sqlite3_int64* seconds) const {
        if (!db_ || child < 1 || child > 3 || !seconds ||
            !facekids_date::valid(day)) return false;
        return statement_int(db_,
            "SELECT max(0,c.limit_seconds + coalesce(q.bonus_seconds,0)"
            " - coalesce(q.used_seconds,0)) FROM children c"
            " LEFT JOIN daily_quota q ON q.child_id=c.id AND q.day=?2"
            " WHERE c.id=?1;",
            child, day, seconds);
    }
    bool set_limit(int child, int minutes) {
        if (!db_ || child < 1 || child > 3 || minutes < 1 || minutes > 1440)
            return false;
        sqlite3_stmt* s = nullptr;
        if (sqlite3_prepare_v2(db_, "UPDATE children SET limit_seconds=?1 WHERE id=?2;",
                               -1, &s, nullptr) != SQLITE_OK) return false;
        bool ok = sqlite3_bind_int(s, 1, minutes * 60) == SQLITE_OK &&
                  sqlite3_bind_int(s, 2, child) == SQLITE_OK &&
                  sqlite3_step(s) == SQLITE_DONE && sqlite3_changes(db_) == 1;
        sqlite3_finalize(s);
        return ok;
    }
    bool charge(int child, const char* day, int seconds) {
        if (!db_ || child < 1 || child > 3 || !facekids_date::valid(day) ||
            seconds <= 0 || seconds > 86400) return false;
        if (!exec(db_, "BEGIN IMMEDIATE;")) return false;
        bool ok = false;
        do {
            sqlite3_stmt* init = nullptr;
            if (sqlite3_prepare_v2(db_,
                "INSERT OR IGNORE INTO daily_quota(child_id,day) VALUES(?1,?2);",
                -1, &init, nullptr) != SQLITE_OK) break;
            bool prepared = sqlite3_bind_int(init, 1, child) == SQLITE_OK &&
                sqlite3_bind_text(init, 2, day, -1, SQLITE_TRANSIENT) == SQLITE_OK &&
                sqlite3_step(init) == SQLITE_DONE;
            sqlite3_finalize(init);
            if (!prepared) break;
            sqlite3_stmt* update = nullptr;
            if (sqlite3_prepare_v2(db_,
                "UPDATE daily_quota SET used_seconds=used_seconds+?3"
                " WHERE child_id=?1 AND day=?2"
                " AND used_seconds+?3 <= bonus_seconds+"
                " (SELECT limit_seconds FROM children WHERE id=?1);",
                -1, &update, nullptr) != SQLITE_OK) break;
            bool changed = sqlite3_bind_int(update, 1, child) == SQLITE_OK &&
                sqlite3_bind_text(update, 2, day, -1, SQLITE_TRANSIENT) == SQLITE_OK &&
                sqlite3_bind_int(update, 3, seconds) == SQLITE_OK &&
                sqlite3_step(update) == SQLITE_DONE &&
                sqlite3_changes(db_) == 1;
            sqlite3_finalize(update);
            if (!changed) break;
            ok = exec(db_, "COMMIT;");
        } while (false);
        if (!ok) exec(db_, "ROLLBACK;");
        return ok;
    }
    bool add_bonus(int child, const char* day, int minutes) {
        if (!db_ || child < 1 || child > 3 || !facekids_date::valid(day) ||
            minutes <= 0 || minutes > 480) return false;
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db_,
            "INSERT INTO daily_quota(child_id,day,bonus_seconds)"
            " VALUES(?1,?2,?3)"
            " ON CONFLICT(child_id,day) DO UPDATE SET"
            " bonus_seconds=bonus_seconds+excluded.bonus_seconds"
            " WHERE bonus_seconds <= 28800-excluded.bonus_seconds;",
            -1, &stmt, nullptr) != SQLITE_OK) return false;
        bool ok = sqlite3_bind_int(stmt, 1, child) == SQLITE_OK &&
                  sqlite3_bind_text(stmt, 2, day, -1, SQLITE_TRANSIENT) == SQLITE_OK &&
                  sqlite3_bind_int(stmt, 3, minutes * 60) == SQLITE_OK &&
                  sqlite3_step(stmt) == SQLITE_DONE &&
                  sqlite3_changes(db_) == 1;
        sqlite3_finalize(stmt);
        return ok;
    }
};

// Resolve the real Windows known folder, not an overridable process
// environment variable (which may point to an unsafe directory).
inline std::wstring program_data_root() {
    PWSTR folder=nullptr;
    HRESULT hr=SHGetKnownFolderPath(FOLDERID_ProgramData, KF_FLAG_DEFAULT,
                                    nullptr, &folder);
    if (FAILED(hr) || !folder) {
        if (folder) CoTaskMemFree(folder);
        return {};
    }
    const std::wstring result=std::wstring(folder)+L"\\FaceControlKidsPC";
    CoTaskMemFree(folder);
    return result;
}
inline bool trusted_root_self_test() {
    const std::wstring expected=program_data_root();
    if (expected.empty()) return false;
    wchar_t original[32768]={};
    DWORD chars=GetEnvironmentVariableW(L"ProgramData", original, 32768);
    if (chars>=32768) return false;
    if (!SetEnvironmentVariableW(L"ProgramData", L"C:\\fake-untrusted-root"))
        return false;
    const std::wstring actual=program_data_root();
    const BOOL restored=SetEnvironmentVariableW(
        L"ProgramData", chars==0 ? nullptr : original);
    return restored && actual==expected;
}

// Negative ACL tests are performed under isolated temporary directories.
inline bool reject_permissive_directory(const std::wstring& path) {
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
        L"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;WD)",
        SDDL_REVISION_1, &descriptor, nullptr)) return false;
    SECURITY_ATTRIBUTES sa = {sizeof(sa), descriptor, FALSE};
    BOOL created = CreateDirectoryW(path.c_str(), &sa);
    LocalFree(descriptor);
    if (!created) return false;
    bool rejected = !allowed_acl(path, true);
    Store store;
    rejected = rejected && !store.open(path);
    RemoveDirectoryW(path.c_str());
    return rejected;
}

inline bool reject_permissive_database(const std::wstring& path) {
    if (!make_secure_directory(path)) return false;
    const std::wstring file = path + L"\\quota.sqlite3";
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
        L"D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;WD)",
        SDDL_REVISION_1, &descriptor, nullptr)) return false;
    SECURITY_ATTRIBUTES sa = {sizeof(sa), descriptor, FALSE};
    HANDLE handle = CreateFileW(file.c_str(), GENERIC_WRITE, 0, &sa,
                                CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    LocalFree(descriptor);
    if (handle == INVALID_HANDLE_VALUE) return false;
    CloseHandle(handle);
    bool rejected = !allowed_acl(file, false);
    Store store;
    rejected = rejected && !store.open(path);
    DeleteFileW(file.c_str());
    RemoveDirectoryW(path.c_str());
    return rejected;
}

inline bool reject_unreadable_sqlite(const std::wstring& folder) {
    if (!make_secure_directory(folder)) return false;
    const std::wstring path=folder + L"\\quota.sqlite3";
    HANDLE handle=CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr,
                              CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle==INVALID_HANDLE_VALUE) return false;
    const char text[]="not-an-sqlite-database";
    DWORD bytes=0;
    BOOL written=WriteFile(handle, text, sizeof(text), &bytes, nullptr);
    CloseHandle(handle);
    Store store;
    bool success=written && bytes==sizeof(text) && !store.open(folder);
    store.close();
    DeleteFileW(path.c_str());
    RemoveDirectoryW(folder.c_str());
    return success;
}

inline bool self_test() {
    if (!trusted_root_self_test() || !facekids_date::self_test()) return false;
    wchar_t tmp[MAX_PATH] = {};
    if (!GetTempPathW(MAX_PATH, tmp)) return false;
    wchar_t testPath[MAX_PATH] = {};
    if (!GetTempFileNameW(tmp, L"FKQ", 0, testPath)) return false;
    if (!DeleteFileW(testPath)) return false;
    const std::wstring folder(testPath);
    if (!make_secure_directory(folder)) return false;
    const std::wstring dbPath = folder + L"\\quota.sqlite3";
    bool success = true;
    const char* today = "2026-10-20";
    const char* tomorrow = "2026-10-21";
    sqlite3_int64 remain = -1;
    {
        Store store;
        success = store.open(folder) &&
            store.remaining(1, today, &remain) && remain == 7200 &&
            store.remaining(2, today, &remain) && remain == 7200 &&
            store.remaining(3, today, &remain) && remain == 7200 &&
            store.charge(1, today, 3600) &&
            store.remaining(1, today, &remain) && remain == 3600 &&
            !store.charge(1, today, 3601) &&
            store.remaining(2, today, &remain) && remain == 7200 &&
            store.charge(2, today, 7200) &&
            !store.charge(2, today, 1) &&
            store.add_bonus(2, today, 30) &&
            store.charge(2, today, 1800) &&
            store.remaining(2, today, &remain) && remain == 0 &&
            store.set_limit(3, 60) &&
            store.remaining(3, today, &remain) && remain == 3600 &&
            store.remaining(1, tomorrow, &remain) && remain == 7200 &&
            !store.charge(1, today, -1) &&
            !store.set_limit(1, 0) &&
            !store.add_bonus(2, today, 481) &&
            !store.add_bonus(2, today, 480) &&
            !store.charge(1, "2026-02-30", 1) &&
            !store.remaining(1, "2026-13-01", &remain) &&
            !store.add_bonus(2, "2026-02-29", 1);
    }
    // Synthetic embedding vectors: no child photos or actual biometrics.
    {
        Store store;
        int count=-1, erased=-1;
        std::array<float,128> first={}, sibling={}, invalid={};
        first[0]=1.0f;
        sibling[1]=1.0f;
        invalid[0]=std::numeric_limits<float>::quiet_NaN();
        success = success && store.open(folder) &&
            store.add_template(1,first) &&
            store.add_template(2,sibling) &&
            !store.add_template(1,invalid) &&
            !store.add_template(1,std::array<float,128>{}) &&
            store.count_templates(1,&count) && count==1 &&
            store.count_templates(2,&count) && count==1;
        for(int i=0;i<4 && success;++i) success=store.add_template(1,first);
        success=success && !store.add_template(1,first) &&
            store.count_templates(1,&count) && count==5 &&
            store.erase_templates(1,&erased) && erased==5 &&
            store.count_templates(1,&count) && count==0 &&
            store.count_templates(2,&count) && count==1 &&
            !store.count_templates(4,&count) &&
            !store.erase_templates(4,&erased) &&
            store.remaining(1,today,&remain) && remain==3600;
    }
    {
        Store reopened;
        int count_verify=-1;
        success = success && reopened.open(folder) &&
            reopened.remaining(1, today, &remain) && remain == 3600 &&
            reopened.remaining(2, today, &remain) && remain == 0 &&
            reopened.remaining(3, today, &remain) && remain == 3600 &&
            reopened.count_templates(2, &count_verify) && count_verify == 1;
    }
    success = success && allowed_acl(folder, true) && allowed_acl(dbPath, false);
    success = success && reject_permissive_directory(folder + L"_loose");
    success = success && reject_permissive_database(folder + L"_unsafe_db");
    success = success && reject_unreadable_sqlite(folder + L"_invalid_db");
    DeleteFileW(dbPath.c_str());
    RemoveDirectoryW(folder.c_str());
    // No ProgramData writes or service installation happen during --self-test.
    return success;
}

} // namespace facekids_quota
