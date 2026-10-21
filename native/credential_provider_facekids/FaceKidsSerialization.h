#pragma once
#include "common.h"
#include <wincred.h>

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
        if (!username || !password || !outBuffer || !outBufferSize || !outAuthPackage) {
            return E_INVALIDARG;
        }

        *outBuffer = nullptr;
        *outBufferSize = 0;
        *outAuthPackage = 0;

        std::wstring fullUser;
        if (wcschr(username, L'\\') != nullptr) {
            fullUser = username;
        } else if (domain && wcslen(domain) > 0) {
            fullUser = std::wstring(domain) + L"\\" + username;
        } else {
            fullUser = std::wstring(L".\\") + username;
        }

        DWORD cbPacked = 0;
        CredPackAuthenticationBufferW(
            0,
            const_cast<LPWSTR>(fullUser.c_str()),
            const_cast<LPWSTR>(password),
            nullptr,
            &cbPacked
        );

        if (cbPacked == 0) {
            LogCP(L"[FaceKidsSerialization] Falha ao consultar tamanho do buffer: erro=%lu", GetLastError());
            return E_FAIL;
        }

        BYTE* buffer = static_cast<BYTE*>(CoTaskMemAlloc(cbPacked));
        if (!buffer) {
            return E_OUTOFMEMORY;
        }

        if (!CredPackAuthenticationBufferW(
            0,
            const_cast<LPWSTR>(fullUser.c_str()),
            const_cast<LPWSTR>(password),
            buffer,
            &cbPacked
        )) {
            LogCP(L"[FaceKidsSerialization] CredPackAuthenticationBufferW falhou: erro=%lu", GetLastError());
            CoTaskMemFree(buffer);
            return E_FAIL;
        }

        HANDLE lsaHandle = nullptr;
        NTSTATUS status = LsaConnectUntrusted(&lsaHandle);
        if (status != 0 || !lsaHandle) {
            LogCP(L"[FaceKidsSerialization] LsaConnectUntrusted falhou: status=0x%lx", status);
            CoTaskMemFree(buffer);
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
            LogCP(L"[FaceKidsSerialization] LsaLookupAuthenticationPackage falhou: status=0x%lx", status);
            CoTaskMemFree(buffer);
            return E_FAIL;
        }

        *outBuffer = buffer;
        *outBufferSize = cbPacked;
        *outAuthPackage = authPackage;
        LogCP(L"[FaceKidsSerialization] Buffer serializado com sucesso: bytes=%lu, authPackage=%lu", cbPacked, authPackage);
        return S_OK;
    }
};
