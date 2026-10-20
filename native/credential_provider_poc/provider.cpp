// FaceKids diagnostic Credential Provider, for isolated COM testing only.
// Not an authenticator: it NEVER returns Windows logon credentials.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <credentialprovider.h>
#include <objbase.h>
#include <new>
#include <cwchar>
#include <cstring>
#include <string>
#include <sddl.h>
#ifdef FACEKIDS_DIAGNOSTIC_HOST_TEST
#include "precheck_client.h"
#endif
static volatile LONG objects=0, locks=0;

static HRESULT clone_text(PCWSTR src, PWSTR* out) {
    if (!out) return E_POINTER;
    *out=nullptr;
    const size_t size=(wcslen(src)+1)*sizeof(WCHAR);
    *out=static_cast<PWSTR>(CoTaskMemAlloc(size));
    if (!*out) return E_OUTOFMEMORY;
    memcpy(*out,src,size);
    return S_OK;
}

class DiagnosticCredential final : public ICredentialProviderCredential2 {
    std::wstring bound_sid_;
    volatile LONG references=1;
public:
    DiagnosticCredential() { InterlockedIncrement(&objects); }
    ~DiagnosticCredential() { InterlockedDecrement(&objects); }
    void BindSid(const std::wstring& sid) { bound_sid_=sid; }
    HRESULT STDMETHODCALLTYPE GetUserSid(PWSTR* sid) override {
        if (!sid) return E_POINTER;
        *sid=nullptr;
        return bound_sid_.empty() ? E_UNEXPECTED : clone_text(bound_sid_.c_str(),sid);
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** out) override {
        if (!out) return E_POINTER;
        *out=nullptr;
        if (iid==IID_IUnknown || iid==IID_ICredentialProviderCredential) {
            *out=static_cast<ICredentialProviderCredential*>(this);
            AddRef(); return S_OK;
        }
        if (iid==IID_ICredentialProviderCredential2) {
            *out=static_cast<ICredentialProviderCredential2*>(this);
            AddRef(); return S_OK;
        }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ULONG(InterlockedIncrement(&references)); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG n=InterlockedDecrement(&references);
        if (!n) delete this;
        return ULONG(n);
    }
    HRESULT STDMETHODCALLTYPE Advise(ICredentialProviderCredentialEvents*) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE UnAdvise() override { return S_OK; }
    HRESULT STDMETHODCALLTYPE SetSelected(BOOL* autoLogon) override {
        if (!autoLogon) return E_POINTER;
        *autoLogon=FALSE;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE SetDeselected() override { return S_OK; }
    HRESULT STDMETHODCALLTYPE GetFieldState(DWORD id,CREDENTIAL_PROVIDER_FIELD_STATE* state,
        CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* interactive) override {
        if (!state || !interactive) return E_POINTER;
        if (id>=2) return E_INVALIDARG;
        *state=CPFS_DISPLAY_IN_SELECTED_TILE;
        *interactive=CPFIS_NONE;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetStringValue(DWORD id,PWSTR* output) override {
        if (!output) return E_POINTER;
        *output=nullptr;
        if (id==0) return clone_text(L"FaceKids - DIAGNOSTICO",output);
        if (id==1) return clone_text(L"Somente teste. Nenhuma senha utilizada.",output);
        return E_INVALIDARG;
    }
    HRESULT STDMETHODCALLTYPE GetBitmapValue(DWORD,HBITMAP*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE GetCheckboxValue(DWORD,BOOL*,PWSTR*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE GetSubmitButtonValue(DWORD,DWORD*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE GetComboBoxValueCount(DWORD,DWORD*,DWORD*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE GetComboBoxValueAt(DWORD,DWORD,PWSTR*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE SetStringValue(DWORD,PCWSTR) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE SetCheckboxValue(DWORD,BOOL) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE SetComboBoxSelectedValue(DWORD,DWORD) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE CommandLinkClicked(DWORD) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE GetSerialization(CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* response,
        CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* serial,PWSTR* status,
        CREDENTIAL_PROVIDER_STATUS_ICON* icon) override {
        if (!response || !serial || !status || !icon) return E_POINTER;
        *response=CPGSR_NO_CREDENTIAL_NOT_FINISHED;
        *serial={};
        *status=nullptr;
        *icon=CPSI_NONE;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE ReportResult(NTSTATUS,NTSTATUS,PWSTR* status,
        CREDENTIAL_PROVIDER_STATUS_ICON* icon) override {
        if (status) *status=nullptr;
        if (icon) *icon=CPSI_NONE;
        return S_OK;
    }
};

// Never enumerate a tile without matching the administratively provisioned SID.
// The isolated COM test build can inject a fake SID, but never authenticates.
#ifdef FACEKIDS_DIAGNOSTIC_HOST_TEST
extern "C" __declspec(dllexport) HRESULT __stdcall FaceKidsDiagnosticPrecheckForHost(
    DWORD session, DWORD child) {
    if (!facekids_cp_client::self_test()) return E_FAIL;
    // In an isolated COM host running as an administrator, PRECHECK must
    // always be denied. The diagnostic DLL never calls GetSerialization.
    return facekids_cp_client::request(session, child) ==
        facekids_cp_client::Precheck::Denied ? S_OK : E_ACCESSDENIED;
}
static std::wstring g_host_test_sid;
extern "C" __declspec(dllexport) HRESULT __stdcall FaceKidsSetDiagnosticSidForHost(PCWSTR sid) {
    if (!sid) return E_POINTER;
    PSID binary=nullptr;
    if (!ConvertStringSidToSidW(sid,&binary)) return E_INVALIDARG;
    LocalFree(binary);
    g_host_test_sid=sid;
    return S_OK;
}
#endif
static std::wstring load_target_sid() {
#ifdef FACEKIDS_DIAGNOSTIC_HOST_TEST
    return g_host_test_sid;
#else
    WCHAR sid[256]={};
    DWORD bytes=sizeof(sid);
    LONG rc=RegGetValueW(HKEY_LOCAL_MACHINE,
        L"SOFTWARE\\FaceControlKidsPC\\CredentialProvider",
        L"TargetUserSid",RRF_RT_REG_SZ,nullptr,sid,&bytes);
    if (rc!=ERROR_SUCCESS || !sid[0]) return {};
    PSID binary=nullptr;
    if (!ConvertStringSidToSidW(sid,&binary)) return {};
    LocalFree(binary);
    return sid;
#endif
}

class DiagnosticProvider final : public ICredentialProvider, public ICredentialProviderSetUserArray {
    bool eligible_=false;
    volatile LONG references=1;
    DiagnosticCredential* credential;
public:
    DiagnosticProvider() : credential(new(std::nothrow) DiagnosticCredential()) {
        InterlockedIncrement(&objects);
    }
    ~DiagnosticProvider() {
        if (credential) credential->Release();
        InterlockedDecrement(&objects);
    }
    bool ready() const { return credential!=nullptr; }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** out) override {
        if (!out) return E_POINTER;
        *out=nullptr;
        if (iid==IID_IUnknown || iid==IID_ICredentialProvider) {
            *out=static_cast<ICredentialProvider*>(this);
            AddRef(); return S_OK;
        }
        if (iid==IID_ICredentialProviderSetUserArray) {
            *out=static_cast<ICredentialProviderSetUserArray*>(this);
            AddRef(); return S_OK;
        }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ULONG(InterlockedIncrement(&references)); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG n=InterlockedDecrement(&references);
        if (!n) delete this;
        return ULONG(n);
    }
    HRESULT STDMETHODCALLTYPE SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO usage,DWORD) override {
        return usage==CPUS_LOGON || usage==CPUS_UNLOCK_WORKSTATION ? S_OK : E_NOTIMPL;
    }
    HRESULT STDMETHODCALLTYPE SetSerialization(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION*) override {
        return E_NOTIMPL;
    }
    HRESULT STDMETHODCALLTYPE Advise(ICredentialProviderEvents*,UINT_PTR) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE UnAdvise() override { return S_OK; }
    // The Windows-provided user list is consulted for an exact SID match.
    HRESULT STDMETHODCALLTYPE SetUserArray(ICredentialProviderUserArray* users) override {
        eligible_=false;
        if (credential) credential->BindSid(L"");
        if (!users) return E_POINTER;
        const std::wstring allowed=load_target_sid();
        if (allowed.empty() || !credential) return S_OK; // fail closed
        DWORD count=0;
        if (FAILED(users->GetCount(&count))) return S_OK;
        for (DWORD i=0;i<count;++i) {
            ICredentialProviderUser* user=nullptr;
            if (FAILED(users->GetAt(i,&user)) || !user) continue;
            PWSTR sid=nullptr;
            HRESULT hr=user->GetSid(&sid);
            if (SUCCEEDED(hr) && sid && _wcsicmp(sid,allowed.c_str())==0) {
                credential->BindSid(sid);
                eligible_=true;
            }
            CoTaskMemFree(sid);
            user->Release();
            if (eligible_) break;
        }
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetFieldDescriptorCount(DWORD* count) override {
        if (!count) return E_POINTER;
        *count=2;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetFieldDescriptorAt(DWORD id,CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** out) override {
        if (!out) return E_POINTER;
        *out=nullptr;
        if (id>=2) return E_INVALIDARG;
        auto* desc=static_cast<CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR*>(
            CoTaskMemAlloc(sizeof(CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR)));
        if (!desc) return E_OUTOFMEMORY;
        *desc={};
        desc->dwFieldID=id;
        desc->cpft=id==0 ? CPFT_LARGE_TEXT : CPFT_SMALL_TEXT;
        HRESULT hr=clone_text(id==0 ? L"FaceKids" : L"Status",&desc->pszLabel);
        if (FAILED(hr)) { CoTaskMemFree(desc); return hr; }
        *out=desc;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetCredentialCount(DWORD* count,DWORD* def,BOOL* autoLogon) override {
        if (!count || !def || !autoLogon) return E_POINTER;
        *count=(credential && eligible_) ? 1 : 0;
        *def=CREDENTIAL_PROVIDER_NO_DEFAULT;
        *autoLogon=FALSE;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetCredentialAt(DWORD id,ICredentialProviderCredential** out) override {
        if (!out) return E_POINTER;
        *out=nullptr;
        if (id!=0 || !credential || !eligible_) return E_INVALIDARG;
        return credential->QueryInterface(IID_ICredentialProviderCredential,reinterpret_cast<void**>(out));
    }
};

class ProviderFactory final : public IClassFactory {
    volatile LONG references=1;
public:
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** out) override {
        if (!out) return E_POINTER;
        *out=nullptr;
        if (iid==IID_IUnknown || iid==IID_IClassFactory) {
            *out=static_cast<IClassFactory*>(this);
            AddRef(); return S_OK;
        }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ULONG(InterlockedIncrement(&references)); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG n=InterlockedDecrement(&references); if (!n) delete this; return ULONG(n);
    }
    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer,REFIID iid,void** out) override {
        if (!out) return E_POINTER;
        *out=nullptr;
        if (outer) return CLASS_E_NOAGGREGATION;
        auto* p=new(std::nothrow) DiagnosticProvider();
        if (!p) return E_OUTOFMEMORY;
        if (!p->ready()) { p->Release(); return E_OUTOFMEMORY; }
        HRESULT hr=p->QueryInterface(iid,out);
        p->Release();
        return hr;
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) override {
        if (lock) InterlockedIncrement(&locks); else InterlockedDecrement(&locks);
        return S_OK;
    }
};
static const CLSID kProviderId={0xfac0d041,0x3dd0,0x4a8c,{0x9f,0x18,0x44,0x0c,0x44,0x33,0x0c,0x10}};
extern "C" __declspec(dllexport) HRESULT __stdcall FaceKidsGetClassObject(
    REFCLSID clsid,REFIID iid,LPVOID* out) {
    if (!out) return E_POINTER;
    *out=nullptr;
    if (clsid!=kProviderId) return CLASS_E_CLASSNOTAVAILABLE;
    auto* f=new(std::nothrow) ProviderFactory();
    if (!f) return E_OUTOFMEMORY;
    HRESULT hr=f->QueryInterface(iid,out);
    f->Release();
    return hr;
}
extern "C" __declspec(dllexport) HRESULT __stdcall FaceKidsCanUnloadNow() {
    return objects==0 && locks==0 ? S_OK : S_FALSE;
}
BOOL APIENTRY DllMain(HMODULE m,DWORD why,LPVOID) {
    if (why==DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(m);
    return TRUE;
}
