#pragma once
#include "common.h"

class FaceKidsSerialization {
public:
    static HRESULT SerializeKerbInteractiveLogon(
        PCWSTR domain,
        PCWSTR username,
        PCWSTR password,
        BYTE** outBuffer,
        DWORD* outBufferSize,
        ULONG* outAuthPackage)
    {
        if (!domain || !username || !password || !outBuffer || !outBufferSize || !outAuthPackage) {
            return E_INVALIDARG;
        }

        *outBuffer = nullptr;
        *outBufferSize = 0;
        *outAuthPackage = 0;

        HANDLE lsaHandle = nullptr;
        NTSTATUS status = LsaConnectUntrusted(&lsaHandle);
        if (status != 0 || !lsaHandle) {
            return E_FAIL;
        }

        LSA_STRING packageName;
        const char* pkgStr = "Negotiate";
        packageName.Buffer = const_cast<PCHAR>(pkgStr);
        packageName.Length = static_cast<USHORT>(strlen(pkgStr));
        packageName.MaximumLength = packageName.Length + 1;

        ULONG authPackage = 0;
        status = LsaLookupAuthenticationPackage(lsaHandle, &packageName, &authPackage);
        LsaDeregisterLogonProcess(lsaHandle);

        if (status != 0) {
            return E_FAIL;
        }

        const DWORD domainLen = static_cast<DWORD>(wcslen(domain));
        const DWORD userLen = static_cast<DWORD>(wcslen(username));
        const DWORD passLen = static_cast<DWORD>(wcslen(password));

        const DWORD domainBytes = domainLen * sizeof(WCHAR);
        const DWORD userBytes = userLen * sizeof(WCHAR);
        const DWORD passBytes = passLen * sizeof(WCHAR);

        const DWORD totalSize = sizeof(KERB_INTERACTIVE_LOGON) + domainBytes + userBytes + passBytes;
        BYTE* buffer = static_cast<BYTE*>(CoTaskMemAlloc(totalSize));
        if (!buffer) {
            return E_OUTOFMEMORY;
        }
        ZeroMemory(buffer, totalSize);

        KERB_INTERACTIVE_LOGON* pLogon = reinterpret_cast<KERB_INTERACTIVE_LOGON*>(buffer);
        pLogon->MessageType = KerbInteractiveLogon;

        BYTE* cursor = buffer + sizeof(KERB_INTERACTIVE_LOGON);

        // Domain
        pLogon->LogonDomainName.Length = static_cast<USHORT>(domainBytes);
        pLogon->LogonDomainName.MaximumLength = static_cast<USHORT>(domainBytes);
        pLogon->LogonDomainName.Buffer = reinterpret_cast<PWSTR>(cursor);
        memcpy(cursor, domain, domainBytes);
        cursor += domainBytes;

        // User
        pLogon->UserName.Length = static_cast<USHORT>(userBytes);
        pLogon->UserName.MaximumLength = static_cast<USHORT>(userBytes);
        pLogon->UserName.Buffer = reinterpret_cast<PWSTR>(cursor);
        memcpy(cursor, username, userBytes);
        cursor += userBytes;

        // Password
        pLogon->Password.Length = static_cast<USHORT>(passBytes);
        pLogon->Password.MaximumLength = static_cast<USHORT>(passBytes);
        pLogon->Password.Buffer = reinterpret_cast<PWSTR>(cursor);
        memcpy(cursor, password, passBytes);

        *outBuffer = buffer;
        *outBufferSize = totalSize;
        *outAuthPackage = authPackage;
        return S_OK;
    }
};
