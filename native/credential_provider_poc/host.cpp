// Safe P0-2: load the DLL using the standard COM entry point in an isolated host.
// Never registers a CLSID or signs anyone into Windows.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <credentialprovider.h>
#include <objbase.h>
#include <cstdio>
#include <initializer_list>

using FactoryEntry = HRESULT (STDAPICALLTYPE*)(REFCLSID, REFIID, void**);
using CanUnloadEntry = HRESULT (STDAPICALLTYPE*)();

static const CLSID kProviderId =
    {0xfac0d041, 0x3dd0, 0x4a8c, {0x9f,0x18,0x44,0x0c,0x44,0x33,0x0c,0x10}};

int wmain(int argc, wchar_t** argv) {
    if (argc != 2) {
        std::fwprintf(stderr, L"usage: FaceKidsProviderHost.exe path-to-DLL\n");
        return 2;
    }
    HRESULT init = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    if (FAILED(init)) return 3;
    int result = 0;
    HMODULE dll = LoadLibraryW(argv[1]);
    if (!dll) {
        std::fprintf(stderr, "FAIL: LoadLibraryW error %lu\n", GetLastError());
        CoUninitialize();
        return 4;
    }
    auto factory_entry = reinterpret_cast<FactoryEntry>(GetProcAddress(dll, "DllGetClassObject"));
    auto can_unload = reinterpret_cast<CanUnloadEntry>(GetProcAddress(dll, "DllCanUnloadNow"));
    if (!factory_entry || !can_unload) {
        std::puts("FAIL: missing standard COM entry points");
        result = 5;
    } else {
        IClassFactory* factory = nullptr;
        HRESULT hr = factory_entry(kProviderId, IID_IClassFactory, reinterpret_cast<void**>(&factory));
        if (FAILED(hr) || !factory) {
            std::printf("FAIL: factory 0x%08lx\n", static_cast<unsigned long>(hr));
            result = 6;
        } else {
            ICredentialProvider* provider = nullptr;
            hr = factory->CreateInstance(nullptr, IID_ICredentialProvider, reinterpret_cast<void**>(&provider));
            if (FAILED(hr) || !provider) {
                std::printf("FAIL: provider 0x%08lx\n", static_cast<unsigned long>(hr));
                result = 7;
            } else {
                for (CREDENTIAL_PROVIDER_USAGE_SCENARIO scenario : {CPUS_LOGON, CPUS_UNLOCK_WORKSTATION}) {
                    DWORD count = 99, def = 0, fields = 99;
                    BOOL auto_logon = TRUE;
                    HRESULT a = provider->SetUsageScenario(scenario, 0);
                    HRESULT b = provider->GetCredentialCount(&count, &def, &auto_logon);
                    HRESULT c = provider->GetFieldDescriptorCount(&fields);
                    if (FAILED(a) || FAILED(b) || FAILED(c) || count != 0 ||
                        def != CREDENTIAL_PROVIDER_NO_DEFAULT || auto_logon != FALSE || fields != 0) {
                        std::printf("FAIL: unexpected credentials/fields in scenario %d\n", int(scenario));
                        result = 8;
                    }
                }
                if (provider->SetUsageScenario(CPUS_CREDUI, 0) != E_NOTIMPL) {
                    std::puts("FAIL: CredUI must remain unsupported");
                    result = 9;
                }
                provider->Release();
            }
            factory->Release();
        }
        if (can_unload() != S_OK) {
            std::puts("FAIL: DLL still has COM references");
            result = 10;
        }
    }
    FreeLibrary(dll);
    CoUninitialize();
    if (!result) std::puts("PASS: COM factory, logon/unlock, zero credentials, clean unload");
    return result;
}
