// P0-9: fixed-size read-only CP-to-broker precondition protocol.
//
// The only operation here is a WTS + quota PRECHECK. Success is explicitly
// NOT a Windows authentication grant. No passwords, facial evidence,
// user-controlled SID or quota balance appear in messages.
#pragma once
#include <windows.h>
#include <cstdint>
#include <cstring>

namespace facekids_ipc {

constexpr uint32_t kMagic = 0x31434b46; // "FKC1" little-endian
constexpr uint16_t kVersion = 1;
constexpr uint16_t kPrecheck = 1;
constexpr uint16_t kEraseTemplates = 2; // elevated parent admin, no Windows login

// Explicit wire length avoids compiler padding and arbitrary JSON parsing.
constexpr DWORD kRequestBytes = 16;
struct Request {
    uint32_t magic = kMagic;
    uint16_t version = kVersion;
    uint16_t command = kPrecheck;
    uint32_t session_id = 0;
    uint32_t child_id = 0;
};
static_assert(sizeof(Request) == kRequestBytes, "Wire format must be 16 bytes");

enum class ParseResult {
    Valid,
    BadLength,
    BadMagic,
    BadVersion,
    BadCommand,
    BadSession,
    BadChild,
};

inline ParseResult parse(const void* data, DWORD size, Request* destination) {
    if (!destination) return ParseResult::BadLength;
    if (size != kRequestBytes || !data) return ParseResult::BadLength;
    Request raw = {};
    std::memcpy(&raw, data, sizeof(raw));
    if (raw.magic != kMagic) return ParseResult::BadMagic;
    if (raw.version != kVersion) return ParseResult::BadVersion;
    if (raw.command != kPrecheck && raw.command != kEraseTemplates)
        return ParseResult::BadCommand;
    if (raw.command == kPrecheck &&
        (!raw.session_id || raw.session_id == 0xffffffff))
        return ParseResult::BadSession;
    // Erasure must NEVER be tied to caller-supplied session identity.
    if (raw.command == kEraseTemplates && raw.session_id != 0)
        return ParseResult::BadSession;
    if (raw.child_id < 1 || raw.child_id > 3)
        return ParseResult::BadChild;
    *destination = raw;
    return ParseResult::Valid;
}

inline bool self_test() {
    Request raw = {};
    raw.session_id = 8;
    raw.child_id = 2;
    Request parsed = {};
    if (parse(&raw, sizeof(raw), &parsed) != ParseResult::Valid ||
        parsed.session_id != 8 || parsed.child_id != 2) return false;
    if (parse(&raw, sizeof(raw) - 1, &parsed) != ParseResult::BadLength ||
        parse(&raw, sizeof(raw) + 1, &parsed) != ParseResult::BadLength ||
        parse(nullptr, sizeof(raw), &parsed) != ParseResult::BadLength ||
        parse(&raw, sizeof(raw), nullptr) != ParseResult::BadLength)
        return false;
    raw.magic = 0;
    if (parse(&raw, sizeof(raw), &parsed) != ParseResult::BadMagic) return false;
    raw.magic = kMagic;
    raw.version = 2;
    if (parse(&raw, sizeof(raw), &parsed) != ParseResult::BadVersion) return false;
    raw.version = kVersion;
    raw.command = 900;
    if (parse(&raw, sizeof(raw), &parsed) != ParseResult::BadCommand) return false;
    raw.command = kPrecheck;
    raw.session_id = 0;
    if (parse(&raw, sizeof(raw), &parsed) != ParseResult::BadSession) return false;
    raw.session_id = 8;
    raw.child_id = 4;
    if (parse(&raw, sizeof(raw), &parsed) != ParseResult::BadChild) return false;
    raw.child_id = 0;
    if (parse(&raw, sizeof(raw), &parsed) != ParseResult::BadChild) return false;
    raw.command = kEraseTemplates;
    raw.session_id = 0;
    raw.child_id = 3;
    if (parse(&raw, sizeof(raw), &parsed) != ParseResult::Valid) return false;
    raw.session_id = 8;
    if (parse(&raw, sizeof(raw), &parsed) != ParseResult::BadSession) return false;
    raw.session_id = 0;
    raw.child_id = 4;
    if (parse(&raw, sizeof(raw), &parsed) != ParseResult::BadChild) return false;
    return true;
}

} // namespace facekids_ipc
