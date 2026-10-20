// P0-11: read-only diagnostic IPC client usable by a future Credential
// Provider, but NOT executed by the current GetSerialization path.
// Returns only a precondition status; no login/authentication authority.
#pragma once
#include <windows.h>
#include <cstring>
#include "../windows_broker_poc/ipc_contract.h"

namespace facekids_cp_client {

enum class Precheck { Denied, ReadyForFacialAssessment };

// Never allow a slow or unresponsive IPC peer to block LogonUI indefinitely.
// Both I/O operations use overlapped handles with bounded waits and cancellation.
inline bool bounded_transfer(HANDLE pipe, bool read, void* buffer, DWORD size,
                             DWORD* transferred) {
    OVERLAPPED ov={};
    ov.hEvent=CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!ov.hEvent) return false;
    *transferred=0;
    BOOL started=read
        ? ReadFile(pipe, buffer, size, transferred, &ov)
        : WriteFile(pipe, buffer, size, transferred, &ov);
    bool success=started!=FALSE;
    if (!success && GetLastError()==ERROR_IO_PENDING) {
        if (WaitForSingleObject(ov.hEvent, 750)==WAIT_OBJECT_0) {
            success=GetOverlappedResult(pipe, &ov, transferred, FALSE)!=FALSE;
        } else {
            CancelIoEx(pipe, &ov);
            DWORD ignored=0;
            GetOverlappedResult(pipe, &ov, &ignored, TRUE);
        }
    }
    CloseHandle(ov.hEvent);
    return success;
}

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
                         FILE_FLAG_OVERLAPPED|SECURITY_SQOS_PRESENT|
                         SECURITY_IMPERSONATION, nullptr);
    if (h==INVALID_HANDLE_VALUE) return Precheck::Denied;
    DWORD written=0, received=0;
    char response[32]={};
    bool ok=bounded_transfer(h, false, &wire, sizeof(wire), &written) &&
        written==sizeof(wire) &&
        bounded_transfer(h, true, response, sizeof(response), &received);
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
