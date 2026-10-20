// Production DLL regression: never register the Credential Provider.
// Load it in a disposable Windows CI process, verify it exposes no
// test-only fake SID setters, supplies zero tiles without OS user binding,
// never enables autologon, and unloads cleanly. This DOES NOT test LogonUI.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <credentialprovider.h>
#include <objbase.h>
#include <cstdio>

using GetFactory = HRESULT (STDAPICALLTYPE*)(REFCLSID, REFIID, void**);
using CanUnload = HRESULT (STDAPICALLTYPE*)();
static const CLSID kProviderId={0xfac0d041,0x3dd0,0x4a8c,
                               {0x9f,0x18,0x44,0x0c,0x44,0x33,0x0c,0x10}};

int wmain(int argc, wchar_t** argv) {
    if(argc!=2) {
        std::puts("Usage: FaceKidsProductionDenyTest.exe FaceKidsDiagnosticProvider.dll");
        return 2;
    }
    const HRESULT com=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    if(FAILED(com)) return 3;
    int exitCode=0;
    HMODULE module=LoadLibraryW(argv[1]);
    if(!module) {
        CoUninitialize();
        return 4;
    }
    // Host-test injection exports must NEVER occur in the production DLL.
    if(GetProcAddress(module,"FaceKidsSetDiagnosticSidForHost") ||
       GetProcAddress(module,"FaceKidsDiagnosticPrecheckForHost")) {
        exitCode=5;
    }
    auto factoryFunction=reinterpret_cast<GetFactory>(
        GetProcAddress(module,"DllGetClassObject"));
    auto unloadFunction=reinterpret_cast<CanUnload>(
        GetProcAddress(module,"DllCanUnloadNow"));
    if(!factoryFunction || !unloadFunction) exitCode=6;

    IClassFactory* factory=nullptr;
    ICredentialProvider* provider=nullptr;
    if(!exitCode) {
        if(FAILED(factoryFunction(kProviderId,IID_IClassFactory,
                     reinterpret_cast<void**>(&factory))) || !factory)
            exitCode=7;
    }
    if(!exitCode) {
        if(FAILED(factory->CreateInstance(nullptr,IID_ICredentialProvider,
                   reinterpret_cast<void**>(&provider))) || !provider)
            exitCode=8;
    }
    if(!exitCode) {
        for(auto scenario : {CPUS_LOGON,CPUS_UNLOCK_WORKSTATION}) {
            DWORD count=999,selected=0;
            BOOL automatic=TRUE;
            ICredentialProviderCredential* tile=nullptr;
            const HRESULT usage=provider->SetUsageScenario(scenario,0);
            const HRESULT n=provider->GetCredentialCount(
                &count,&selected,&automatic);
            const HRESULT tileResult=provider->GetCredentialAt(0,&tile);
            if(tile) tile->Release();
            if(usage!=S_OK || n!=S_OK || count!=0 ||
               selected!=CREDENTIAL_PROVIDER_NO_DEFAULT ||
               automatic || tileResult!=E_INVALIDARG || tile)
                exitCode=9;
        }
        if(provider->SetUsageScenario(CPUS_CREDUI,0)!=E_NOTIMPL)
            exitCode=10;
    }
    if(provider) provider->Release();
    if(factory) factory->Release();
    if(!exitCode && unloadFunction()!=S_OK) exitCode=11;
    FreeLibrary(module);
    CoUninitialize();
    if(exitCode) std::printf("FAIL: production provider negative host regression %d\n",exitCode);
    else std::puts("PASS: production provider cannot auto-logon, no test SID hooks, zero unbound tiles");
    return exitCode;
}
