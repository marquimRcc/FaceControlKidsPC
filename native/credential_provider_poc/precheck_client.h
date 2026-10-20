// P0-11: read-only diagnostic IPC client usable by a future Credential
// Provider, but NOT executed by the current GetSerialization path.
// Returns only a precondition status; no login/authentication authority.
#pragma once
#include <windows.h>
#include <cstring>
#include "../windows_broker_poc/ipc_contract.h"

namespace facekids_cp_client {

enum class Precheck { Denied, ReadyForFacialAssessment };

inline Precheck request(DWORD session_id, DWORD child_id) {
    facekids_ipc::Request wire={};
    wire.session_id=session_id;
    wire.child_id=child_id;
    if (facekids_ipc::parse(&wire, sizeof(wire), &wire)
        != facekids_ipc::ParseResult::Valid)
        return Precheck::Denied;
    // The reader must never authenticate users on the strength of this
    // response, and no application in the Filhos session receives a token.
    constexpr wchar_t pipe[] = LR"(\\.\pipe\FaceKidsBrokerPoc-v1)";
    if (!WaitNamedPipeW(pipe, 250)) return Precheck::Denied;
    HANDLE h=CreateFileW(pipe, GENERIC_READ|GENERIC_WRITE, 0, nullptr,
                         OPEN_EXISTING,
                         SECURITY_SQOS_PRESENT|SECURITY_IMPERSONATION, nullptr);
    if (h==INVALID_HANDLE_VALUE) return Precheck::Denied;
    DWORD written=0, received=0;
    char response[32]={};
    bool ok=WriteFile(h, &wire, sizeof(wire), &written, nullptr) &&
        written==sizeof(wire) &&
        ReadFile(h, response, sizeof(response), &received, nullptr);
    CloseHandle(h);
    if (ok && received==13 && std::memcmp(response,"PRECHECK_ONLY",13)==0)
        return Precheck::ReadyForFacialAssessment;
    return Precheck::Denied;
}

inline bool self_test() {
    // Invalid wire requests never touch the operating system.
    return request(0,1)==Precheck::Denied &&
           request(0xffffffff,1)==Precheck::Denied &&
           request(7,0)==Precheck::Denied &&
           request(7,4)==Precheck::Denied;
}

} // namespace facekids_cp_client
