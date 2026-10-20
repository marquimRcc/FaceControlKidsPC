// Diagnostic provider test host: no registration, no LogonUI, no passwords.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <credentialprovider.h>
#include <objbase.h>
#include <cstdio>
#include <initializer_list>
#include <string>
#include <vector>
#include <propidl.h>

using FactoryEntry=HRESULT (STDAPICALLTYPE*)(REFCLSID,REFIID,void**);
using UnloadEntry=HRESULT (STDAPICALLTYPE*)();
static const CLSID kProviderId={0xfac0d041,0x3dd0,0x4a8c,{0x9f,0x18,0x44,0x0c,0x44,0x33,0x0c,0x10}};

// Minimal mocked Windows account list; no real accounts are changed.
class MockUser final : public ICredentialProviderUser {
    volatile LONG refs=1;
    std::wstring sid_;
public:
    explicit MockUser(const std::wstring& sid) : sid_(sid) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id,void** out) override {
        if (!out) return E_POINTER;
        *out=nullptr;
        if (id!=IID_IUnknown && id!=IID_ICredentialProviderUser) return E_NOINTERFACE;
        *out=static_cast<ICredentialProviderUser*>(this);
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ULONG(InterlockedIncrement(&refs)); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG n=InterlockedDecrement(&refs);
        if (!n) delete this;
        return ULONG(n);
    }
    HRESULT STDMETHODCALLTYPE GetSid(PWSTR* out) override {
        if (!out) return E_POINTER;
        *out=nullptr;
        size_t bytes=(sid_.size()+1)*sizeof(wchar_t);
        *out=static_cast<PWSTR>(CoTaskMemAlloc(bytes));
        if (!*out) return E_OUTOFMEMORY;
        memcpy(*out,sid_.c_str(),bytes);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetProviderID(GUID* out) override {
        if (!out) return E_POINTER;
        *out={};
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetStringValue(REFPROPERTYKEY,PWSTR* out) override {
        if (out) *out=nullptr;
        return E_NOTIMPL;
    }
    HRESULT STDMETHODCALLTYPE GetValue(REFPROPERTYKEY,PROPVARIANT* out) override {
        if (out) *out={};
        return E_NOTIMPL;
    }
};
class MockUsers final : public ICredentialProviderUserArray {
    volatile LONG refs=1;
    std::vector<std::wstring> sids_;
public:
    MockUsers(std::initializer_list<PCWSTR> v) : sids_(v.begin(),v.end()) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id,void** out) override {
        if (!out) return E_POINTER;
        *out=nullptr;
        if (id!=IID_IUnknown && id!=IID_ICredentialProviderUserArray) return E_NOINTERFACE;
        *out=static_cast<ICredentialProviderUserArray*>(this);
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ULONG(InterlockedIncrement(&refs)); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG n=InterlockedDecrement(&refs);
        if (!n) delete this;
        return ULONG(n);
    }
    HRESULT STDMETHODCALLTYPE SetProviderFilter(REFGUID) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE GetAccountOptions(CREDENTIAL_PROVIDER_ACCOUNT_OPTIONS* out) override {
        if (!out) return E_POINTER;
        *out=CPAO_NONE; return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetCount(DWORD* out) override {
        if (!out) return E_POINTER;
        *out=DWORD(sids_.size()); return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetAt(DWORD index,ICredentialProviderUser** out) override {
        if (!out) return E_POINTER;
        *out=nullptr;
        if (index>=sids_.size()) return E_INVALIDARG;
        *out=new(std::nothrow) MockUser(sids_[index]);
        return *out ? S_OK : E_OUTOFMEMORY;
    }
};
static bool provide_users(ICredentialProvider* provider,std::initializer_list<PCWSTR> sids) {
    ICredentialProviderSetUserArray* setter=nullptr;
    HRESULT hr=provider->QueryInterface(IID_ICredentialProviderSetUserArray,
        reinterpret_cast<void**>(&setter));
    if (FAILED(hr) || !setter) return false;
    auto* users=new(std::nothrow) MockUsers(sids);
    if (!users) { setter->Release(); return false; }
    hr=setter->SetUserArray(users);
    users->Release();
    setter->Release();
    return hr==S_OK;
}
static bool check_count(ICredentialProvider* p,DWORD expected) {
    DWORD count=99,def=0;
    BOOL autoLogon=TRUE;
    return p->GetCredentialCount(&count,&def,&autoLogon)==S_OK &&
        count==expected && def==CREDENTIAL_PROVIDER_NO_DEFAULT && !autoLogon;
}

static bool verify_tile(ICredentialProviderCredential* c) {
    BOOL autoLogon=TRUE;
    if (c->SetSelected(&autoLogon)!=S_OK || autoLogon) return false;
    ICredentialProviderCredential2* v2=nullptr;
    if (FAILED(c->QueryInterface(IID_ICredentialProviderCredential2,
            reinterpret_cast<void**>(&v2))) || !v2) return false;
    PWSTR sid=nullptr;
    HRESULT sh=v2->GetUserSid(&sid);
    bool sid_ok=(sh==S_OK && sid && wcscmp(sid,L"S-1-5-21-101-202-303-1001")==0);
    CoTaskMemFree(sid);
    v2->Release();
    if (!sid_ok) return false;
    for (DWORD i=0;i<2;++i) {
        CREDENTIAL_PROVIDER_FIELD_STATE state=CPFS_HIDDEN;
        CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE interactive=CPFIS_NONE;
        PWSTR text=nullptr;
        if (c->GetFieldState(i,&state,&interactive)!=S_OK ||
            state!=CPFS_DISPLAY_IN_SELECTED_TILE ||
            c->GetStringValue(i,&text)!=S_OK || !text || !*text) {
            CoTaskMemFree(text); return false;
        }
        CoTaskMemFree(text);
    }
    CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE response=CPGSR_RETURN_CREDENTIAL_FINISHED;
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION serialized{};
    PWSTR status=nullptr;
    CREDENTIAL_PROVIDER_STATUS_ICON icon=CPSI_NONE;
    HRESULT hr=c->GetSerialization(&response,&serialized,&status,&icon);
    if (hr!=S_OK || response!=CPGSR_NO_CREDENTIAL_NOT_FINISHED ||
        serialized.cbSerialization || serialized.rgbSerialization ||
        serialized.ulAuthenticationPackage || status) {
        CoTaskMemFree(status); return false;
    }
    if (c->GetSerialization(nullptr,&serialized,&status,&icon)!=E_POINTER) return false;
    return c->SetDeselected()==S_OK;
}

int wmain(int argc,wchar_t** argv) {
    if (argc!=2) { fwprintf(stderr,L"Usage: FaceKidsProviderHost.exe path-to-DLL\n"); return 2; }
    HRESULT init=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    if (FAILED(init)) return 3;
    HMODULE dll=LoadLibraryW(argv[1]);
    if (!dll) { CoUninitialize(); return 4; }
    int result=0;
    auto make=reinterpret_cast<FactoryEntry>(GetProcAddress(dll,"DllGetClassObject"));
    auto unload=reinterpret_cast<UnloadEntry>(GetProcAddress(dll,"DllCanUnloadNow"));
    auto setup=reinterpret_cast<HRESULT (STDAPICALLTYPE*)(PCWSTR)>(
        GetProcAddress(dll,"FaceKidsSetDiagnosticSidForHost"));
    if (!make || !unload || !setup) result=5;
    else if (setup(L"S-1-5-21-101-202-303-1001")!=S_OK) result=15;
    else {
        IClassFactory* factory=nullptr;
        if (FAILED(make(kProviderId,IID_IClassFactory,reinterpret_cast<void**>(&factory))) || !factory) result=6;
        else {
            ICredentialProvider* provider=nullptr;
            if (FAILED(factory->CreateInstance(nullptr,IID_ICredentialProvider,reinterpret_cast<void**>(&provider)))
                || !provider) result=7;
            else {
                for (auto usage : {CPUS_LOGON,CPUS_UNLOCK_WORKSTATION}) {
                    if (!check_count(provider,0)) result=16;
                    if (!provide_users(provider,{L"S-1-5-21-101-202-303-500"}) ||
                        !check_count(provider,0)) result=17;
                    if (!provide_users(provider,{L"S-1-5-21-101-202-303-500",
                        L"S-1-5-21-101-202-303-1001"}) || !check_count(provider,1))
                        result=18;
                    DWORD count=99,def=0,fields=99;
                    BOOL autologon=TRUE;
                    if (provider->SetUsageScenario(usage,0)!=S_OK ||
                        provider->GetCredentialCount(&count,&def,&autologon)!=S_OK ||
                        provider->GetFieldDescriptorCount(&fields)!=S_OK ||
                        count!=1 || fields!=2 || def!=CREDENTIAL_PROVIDER_NO_DEFAULT || autologon) result=8;
                    for (DWORD i=0;i<2;++i) {
                        CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR* field=nullptr;
                        if (provider->GetFieldDescriptorAt(i,&field)!=S_OK || !field ||
                            field->dwFieldID!=i || !field->pszLabel ||
                            field->cpft!=(i==0 ? CPFT_LARGE_TEXT : CPFT_SMALL_TEXT)) result=9;
                        if (field) { CoTaskMemFree(field->pszLabel); CoTaskMemFree(field); }
                    }
                    ICredentialProviderCredential* credential=nullptr;
                    if (provider->GetCredentialAt(0,&credential)!=S_OK || !credential) result=10;
                    else {
                        if (!verify_tile(credential)) result=11;
                        credential->Release();
                    }
                    credential=nullptr;
                    if (provider->GetCredentialAt(1,&credential)!=E_INVALIDARG || credential) result=12;
                    if (!provide_users(provider,{L"S-1-5-21-101-202-303-500"}) ||
                        !check_count(provider,0)) result=19;
                    credential=nullptr;
                    if (provider->GetCredentialAt(0,&credential)!=E_INVALIDARG || credential) result=20;
                }
                if (provider->SetUsageScenario(CPUS_CREDUI,0)!=E_NOTIMPL) result=13;
                provider->Release();
            }
            factory->Release();
        }
        if (unload()!=S_OK) result=14;
    }
    FreeLibrary(dll);
    CoUninitialize();
    if (result) std::printf("FAIL: COM diagnostic tile test: %d\n",result);
    else std::puts("PASS: read-only diagnostic tile, zero authentication data, correct COM lifecycle");
    return result;
}
