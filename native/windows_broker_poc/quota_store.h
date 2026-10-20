// P0-8 Windows broker quota storage. NOT an IPC endpoint or login unlocker.
// Uses Microsoft-maintained WinSQLite (Windows 10/11) in ProgramData under
// an explicit DACL containing ONLY LocalSystem and Administrators.
// No biometric templates, password material or user-controlled filesystem paths.
#pragma once
#include <windows.h>
#include <aclapi.h>
#include <sddl.h>
#include <winsqlite/winsqlite3.h>
#include <string>
#include <cstdint>
#include <cstdio>
#include <cwchar>
#include <cstring>

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
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    DWORD err = GetNamedSecurityInfoW(
        const_cast<LPWSTR>(path.c_str()), SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION, nullptr, nullptr, &acl, nullptr, &descriptor);
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
    bool systemFound = false, adminsFound = false;
    if (valid) {
        ACL_SIZE_INFORMATION info = {};
        valid = GetAclInformation(acl, &info, sizeof(info), AclSizeInformation) != FALSE;
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
            if (EqualSid(who, sys)) systemFound = true;
            else if (EqualSid(who, adm)) adminsFound = true;
            else valid = false;
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
            !exec(db_, "PRAGMA journal_mode=DELETE;") ||
            !exec(db_, "PRAGMA foreign_keys=ON;") ||
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
            !exec(db_, "INSERT OR IGNORE INTO children(id,limit_seconds) VALUES"
                       "(1,7200),(2,7200),(3,7200);")) {
            close(); return false;
        }
        return true;
    }
    bool remaining(int child, const char* day, sqlite3_int64* seconds) const {
        if (!db_ || child < 1 || child > 3 || !day || !seconds ||
            std::strlen(day) != 10) return false;
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
        if (!db_ || child < 1 || child > 3 || !day || std::strlen(day) != 10 ||
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
        if (!db_ || child < 1 || child > 3 || !day || std::strlen(day) != 10 ||
            minutes <= 0 || minutes > 480) return false;
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db_,
            "INSERT INTO daily_quota(child_id,day,bonus_seconds)"
            " VALUES(?1,?2,?3)"
            " ON CONFLICT(child_id,day) DO UPDATE SET"
            " bonus_seconds=bonus_seconds+excluded.bonus_seconds;",
            -1, &stmt, nullptr) != SQLITE_OK) return false;
        bool ok = sqlite3_bind_int(stmt, 1, child) == SQLITE_OK &&
                  sqlite3_bind_text(stmt, 2, day, -1, SQLITE_TRANSIENT) == SQLITE_OK &&
                  sqlite3_bind_int(stmt, 3, minutes * 60) == SQLITE_OK &&
                  sqlite3_step(stmt) == SQLITE_DONE;
        sqlite3_finalize(stmt);
        return ok;
    }
};

inline std::wstring program_data_root() {
    wchar_t base[32768] = {};
    DWORD length = GetEnvironmentVariableW(L"ProgramData", base,
                                           static_cast<DWORD>(sizeof(base)/sizeof(base[0])));
    if (!length || length >= sizeof(base)/sizeof(base[0])) return {};
    return std::wstring(base) + L"\\FaceControlKidsPC";
}
inline bool self_test() {
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
            !store.add_bonus(2, today, 481);
    }
    {
        Store reopened;
        success = success && reopened.open(folder) &&
            reopened.remaining(1, today, &remain) && remain == 3600 &&
            reopened.remaining(2, today, &remain) && remain == 0 &&
            reopened.remaining(3, today, &remain) && remain == 3600;
    }
    success = success && allowed_acl(folder, true) && allowed_acl(dbPath, false);
    DeleteFileW(dbPath.c_str());
    RemoveDirectoryW(folder.c_str());
    // No ProgramData writes or service installation happen during --self-test.
    return success;
}

} // namespace facekids_quota
