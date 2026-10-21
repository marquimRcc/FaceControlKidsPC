#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <credentialprovider.h>
#include <iostream>

static const CLSID CLSID_FaceKidsProvider = {
    0xfac0d042, 0x3dd0, 0x4a8c, { 0x9f, 0x18, 0x44, 0x0c, 0x44, 0x33, 0x0c, 0x20 }
};

typedef HRESULT (__stdcall *PFN_DllGetClassObject)(REFCLSID, REFIID, LPVOID*);

int main() {
    std::wcout << L"[FaceKids Host Test] Carregando FaceKidsCredentialProvider.dll...\n";
    HMODULE hMod = LoadLibraryW(L"FaceKidsCredentialProvider.dll");
    if (!hMod) {
        std::wcerr << L"[ERRO] Falha ao carregar DLL (codigo " << GetLastError() << L")\n";
        return 1;
    }

    auto pfnDllGetClassObject = (PFN_DllGetClassObject)GetProcAddress(hMod, "DllGetClassObject");
    if (!pfnDllGetClassObject) {
        std::wcerr << L"[ERRO] DllGetClassObject nao encontrado!\n";
        FreeLibrary(hMod);
        return 2;
    }

    IClassFactory* pFactory = nullptr;
    HRESULT hr = pfnDllGetClassObject(CLSID_FaceKidsProvider, IID_IClassFactory, (void**)&pFactory);
    if (FAILED(hr) || !pFactory) {
        std::wcerr << L"[ERRO] Falha ao obter IClassFactory (0x" << std::hex << hr << L")\n";
        FreeLibrary(hMod);
        return 3;
    }

    ICredentialProvider* pProvider = nullptr;
    hr = pFactory->CreateInstance(nullptr, IID_ICredentialProvider, (void**)&pProvider);
    pFactory->Release();
    if (FAILED(hr) || !pProvider) {
        std::wcerr << L"[ERRO] Falha em CreateInstance ICredentialProvider (0x" << std::hex << hr << L")\n";
        FreeLibrary(hMod);
        return 4;
    }

    std::wcout << L"[OK] ICredentialProvider criado com sucesso!\n";

    hr = pProvider->SetUsageScenario(CPUS_UNLOCK_WORKSTATION, 0);
    std::wcout << L"[OK] SetUsageScenario(CPUS_UNLOCK_WORKSTATION): 0x" << std::hex << hr << L"\n";

    DWORD fieldCount = 0;
    pProvider->GetFieldDescriptorCount(&fieldCount);
    std::wcout << L"[OK] Contagem de campos UI: " << fieldCount << L"\n";

    for (DWORD i = 0; i < fieldCount; ++i) {
        CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR* desc = nullptr;
        if (SUCCEEDED(pProvider->GetFieldDescriptorAt(i, &desc)) && desc) {
            std::wcout << L"     - Campo " << i << L": \"" << (desc->pszLabel ? desc->pszLabel : L"") << L"\"\n";
            CoTaskMemFree(desc->pszLabel);
            CoTaskMemFree(desc);
        }
    }

    pProvider->Release();
    FreeLibrary(hMod);
    std::wcout << L"[TESTE PASSOU] FaceKidsCredentialProvider.dll esta valida e funcionando perfeitamente!\n";
    return 0;
}
