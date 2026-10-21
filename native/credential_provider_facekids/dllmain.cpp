#define INITGUID
#include "common.h"
#include "FaceKidsProvider.h"

volatile LONG g_cObjects = 0;
volatile LONG g_cLocks = 0;
static HMODULE g_hModule = nullptr;

class ProviderFactory final : public IClassFactory {
private:
    volatile LONG m_cRef = 1;
public:
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        *ppv = nullptr;
        if (riid == IID_IUnknown || riid == IID_IClassFactory) {
            *ppv = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        return E_NOINTERFACE;
    }

    ULONG STDMETHODCALLTYPE AddRef() override {
        return static_cast<ULONG>(InterlockedIncrement(&m_cRef));
    }

    ULONG STDMETHODCALLTYPE Release() override {
        LONG n = InterlockedDecrement(&m_cRef);
        if (n == 0) delete this;
        return static_cast<ULONG>(n);
    }

    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* pUnkOuter, REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        *ppv = nullptr;
        if (pUnkOuter) return CLASS_E_NOAGGREGATION;

        auto* pProvider = new(std::nothrow) FaceKidsProvider();
        if (!pProvider) return E_OUTOFMEMORY;
        if (!pProvider->IsValid()) {
            pProvider->Release();
            return E_OUTOFMEMORY;
        }

        HRESULT hr = pProvider->QueryInterface(riid, ppv);
        pProvider->Release();
        return hr;
    }

    HRESULT STDMETHODCALLTYPE LockServer(BOOL fLock) override {
        if (fLock) {
            InterlockedIncrement(&g_cLocks);
        } else {
            InterlockedDecrement(&g_cLocks);
        }
        return S_OK;
    }
};

extern "C" __declspec(dllexport) HRESULT __stdcall DllGetClassObject(REFCLSID rclsid, REFIID riid, LPVOID* ppv) {
    if (!ppv) return E_POINTER;
    *ppv = nullptr;
    if (rclsid != CLSID_FaceKidsProvider) return CLASS_E_CLASSNOTAVAILABLE;

    auto* pFactory = new(std::nothrow) ProviderFactory();
    if (!pFactory) return E_OUTOFMEMORY;

    HRESULT hr = pFactory->QueryInterface(riid, ppv);
    pFactory->Release();
    return hr;
}

extern "C" __declspec(dllexport) HRESULT __stdcall DllCanUnloadNow() {
    return (g_cObjects == 0 && g_cLocks == 0) ? S_OK : S_FALSE;
}

static const WCHAR kClsidString[] = L"{FAC0D042-3DD0-4A8C-9F18-440C44330C20}";

extern "C" __declspec(dllexport) HRESULT __stdcall DllRegisterServer() {
    WCHAR szModule[MAX_PATH] = {};
    if (!GetModuleFileNameW(g_hModule, szModule, MAX_PATH)) {
        return HRESULT_FROM_WIN32(GetLastError());
    }

    // 1. HKCR\CLSID\{...}
    std::wstring clsidKey = L"CLSID\\" + std::wstring(kClsidString);
    HKEY hKey = nullptr;
    if (RegCreateKeyExW(HKEY_CLASSES_ROOT, clsidKey.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &hKey, nullptr) == ERROR_SUCCESS) {
        const WCHAR desc[] = L"FaceKids Credential Provider";
        RegSetValueExW(hKey, nullptr, 0, REG_SZ, reinterpret_cast<const BYTE*>(desc), sizeof(desc));

        HKEY hSubKey = nullptr;
        if (RegCreateKeyExW(hKey, L"InprocServer32", 0, nullptr, 0, KEY_WRITE, nullptr, &hSubKey, nullptr) == ERROR_SUCCESS) {
            RegSetValueExW(hSubKey, nullptr, 0, REG_SZ, reinterpret_cast<const BYTE*>(szModule), (DWORD)(wcslen(szModule) + 1) * sizeof(WCHAR));
            const WCHAR threading[] = L"Apartment";
            RegSetValueExW(hSubKey, L"ThreadingModel", 0, REG_SZ, reinterpret_cast<const BYTE*>(threading), sizeof(threading));
            RegCloseKey(hSubKey);
        }
        RegCloseKey(hKey);
    }

    // 2. HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\{...}
    std::wstring cpKey = L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\Credential Providers\\" + std::wstring(kClsidString);
    if (RegCreateKeyExW(HKEY_LOCAL_MACHINE, cpKey.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &hKey, nullptr) == ERROR_SUCCESS) {
        const WCHAR desc[] = L"FaceKidsProvider";
        RegSetValueExW(hKey, nullptr, 0, REG_SZ, reinterpret_cast<const BYTE*>(desc), sizeof(desc));
        RegCloseKey(hKey);
    }

    return S_OK;
}

extern "C" __declspec(dllexport) HRESULT __stdcall DllUnregisterServer() {
    // 1. Remover do Credential Providers
    std::wstring cpKey = L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\Credential Providers\\" + std::wstring(kClsidString);
    RegDeleteKeyW(HKEY_LOCAL_MACHINE, cpKey.c_str());

    // 2. Remover do CLSID
    std::wstring inprocKey = L"CLSID\\" + std::wstring(kClsidString) + L"\\InprocServer32";
    RegDeleteKeyW(HKEY_CLASSES_ROOT, inprocKey.c_str());
    std::wstring clsidKey = L"CLSID\\" + std::wstring(kClsidString);
    RegDeleteKeyW(HKEY_CLASSES_ROOT, clsidKey.c_str());

    return S_OK;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID) {
    if (ul_reason_for_call == DLL_PROCESS_ATTACH) {
        g_hModule = hModule;
        DisableThreadLibraryCalls(hModule);
    }
    return TRUE;
}
