// Diagnostic provider test host: no registration, no LogonUI, no passwords.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <credentialprovider.h>
#include <objbase.h>
#include <cstdio>
#include <initializer_list>

using FactoryEntry=HRESULT (STDAPICALLTYPE*)(REFCLSID,REFIID,void**);
using UnloadEntry=HRESULT (STDAPICALLTYPE*)();
static const CLSID kProviderId={0xfac0d041,0x3dd0,0x4a8c,{0x9f,0x18,0x44,0x0c,0x44,0x33,0x0c,0x10}};

static bool verify_tile(ICredentialProviderCredential* c) {
    BOOL autoLogon=TRUE;
    if (c->SetSelected(&autoLogon)!=S_OK || autoLogon) return false;
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
    if (!make || !unload) result=5;
    else {
        IClassFactory* factory=nullptr;
        if (FAILED(make(kProviderId,IID_IClassFactory,reinterpret_cast<void**>(&factory))) || !factory) result=6;
        else {
            ICredentialProvider* provider=nullptr;
            if (FAILED(factory->CreateInstance(nullptr,IID_ICredentialProvider,reinterpret_cast<void**>(&provider)))
                || !provider) result=7;
            else {
                for (auto usage : {CPUS_LOGON,CPUS_UNLOCK_WORKSTATION}) {
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
