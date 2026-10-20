// Experimental, non-installable Credential Provider skeleton.
// This DLL deliberately returns ZERO credentials, accepts no password,
// and MUST NOT be registered on the host system.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <credentialprovider.h>
#include <new>

static HMODULE g_module = nullptr;
static volatile LONG g_objects = 0;
static volatile LONG g_locks = 0;

class EmptyProvider final : public ICredentialProvider {
    volatile LONG refs_ = 1;
    CREDENTIAL_PROVIDER_USAGE_SCENARIO scenario_ = CPUS_INVALID;
public:
    EmptyProvider() { InterlockedIncrement(&g_objects); }
    ~EmptyProvider() { InterlockedDecrement(&g_objects); }

    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** result) override {
        if (!result) return E_POINTER;
        *result = nullptr;
        if (IsEqualIID(iid, IID_IUnknown) || IsEqualIID(iid, IID_ICredentialProvider)) {
            *result = static_cast<ICredentialProvider*>(this);
            AddRef();
            return S_OK;
        }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override {
        return static_cast<ULONG>(InterlockedIncrement(&refs_));
    }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG count = InterlockedDecrement(&refs_);
        if (count == 0) delete this;
        return static_cast<ULONG>(count);
    }
    HRESULT STDMETHODCALLTYPE SetUsageScenario(
        CREDENTIAL_PROVIDER_USAGE_SCENARIO scenario, DWORD) override {
        if (scenario == CPUS_LOGON || scenario == CPUS_UNLOCK_WORKSTATION) {
            scenario_ = scenario;
            return S_OK;
        }
        return E_NOTIMPL;
    }
    HRESULT STDMETHODCALLTYPE SetSerialization(
        const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION*) override {
        return E_NOTIMPL;
    }
    HRESULT STDMETHODCALLTYPE Advise(
        ICredentialProviderEvents*, UINT_PTR) override {
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE UnAdvise() override {
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetFieldDescriptorCount(DWORD* count) override {
        if (!count) return E_POINTER;
        *count = 0;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetFieldDescriptorAt(
        DWORD, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** field) override {
        if (!field) return E_POINTER;
        *field = nullptr;
        return E_INVALIDARG;
    }
    HRESULT STDMETHODCALLTYPE GetCredentialCount(
        DWORD* count, DWORD* defaultIndex, BOOL* autoLogon) override {
        if (!count || !defaultIndex || !autoLogon) return E_POINTER;
        *count = 0;
        *defaultIndex = CREDENTIAL_PROVIDER_NO_DEFAULT;
        *autoLogon = FALSE;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetCredentialAt(
        DWORD, ICredentialProviderCredential** cred) override {
        if (!cred) return E_POINTER;
        *cred = nullptr;
        return E_INVALIDARG;
    }
};

class ProviderFactory final : public IClassFactory {
    volatile LONG refs_ = 1;
public:
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** result) override {
        if (!result) return E_POINTER;
        *result = nullptr;
        if (IsEqualIID(iid, IID_IUnknown) || IsEqualIID(iid, IID_IClassFactory)) {
            *result = static_cast<IClassFactory*>(this);
            AddRef(); return S_OK;
        }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override {
        return static_cast<ULONG>(InterlockedIncrement(&refs_));
    }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG count = InterlockedDecrement(&refs_);
        if (!count) delete this;
        return static_cast<ULONG>(count);
    }
    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer, REFIID iid, void** result) override {
        if (outer) return CLASS_E_NOAGGREGATION;
        if (!result) return E_POINTER;
        *result = nullptr;
        auto* provider = new (std::nothrow) EmptyProvider();
        if (!provider) return E_OUTOFMEMORY;
        HRESULT status = provider->QueryInterface(iid, result);
        provider->Release();
        return status;
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) override {
        if (lock) InterlockedIncrement(&g_locks);
        else InterlockedDecrement(&g_locks);
        return S_OK;
    }
};

static const CLSID kClassId =
    {0xfac0d041, 0x3dd0, 0x4a8c, {0x9f,0x18,0x44,0x0c,0x44,0x33,0x0c,0x10}};

extern "C" HRESULT __stdcall DllGetClassObject(REFCLSID clsid, REFIID iid, LPVOID* result) {
    if (!result) return E_POINTER;
    *result = nullptr;
    if (!IsEqualCLSID(clsid, kClassId)) return CLASS_E_CLASSNOTAVAILABLE;
    auto* factory = new (std::nothrow) ProviderFactory();
    if (!factory) return E_OUTOFMEMORY;
    HRESULT status = factory->QueryInterface(iid, result);
    factory->Release();
    return status;
}
extern "C" HRESULT __stdcall DllCanUnloadNow() {
    return (g_objects == 0 && g_locks == 0) ? S_OK : S_FALSE;
}
BOOL APIENTRY DllMain(HMODULE module, DWORD why, LPVOID) {
    if (why == DLL_PROCESS_ATTACH) {
        g_module = module;
        DisableThreadLibraryCalls(module);
    }
    return TRUE;
}
