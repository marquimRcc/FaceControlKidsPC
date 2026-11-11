#pragma once
#include "common.h"

class SafePCKidsCredential;

class SafePCKidsProvider final : public ICredentialProvider, public ICredentialProviderSetUserArray {
private:
    volatile LONG m_cRef = 1;
    SafePCKidsCredential* m_pCredential = nullptr;
    ICredentialProviderEvents* m_pEvents = nullptr;
    UINT_PTR m_upAdviseContext = 0;
    CRITICAL_SECTION m_cs;
    bool m_eligible = false;
    bool m_readyToAutoLogon = false;
    std::wstring m_targetSid;

    std::wstring ResolveTargetSid();

public:
    SafePCKidsProvider();
    ~SafePCKidsProvider();

    bool IsValid() const { return m_pCredential != nullptr; }
    void NotifyAuthSuccess();
    bool IsAutoLogonReady();
    void ResetAuth();
    bool TryAddRef();
#ifdef SAFEPCKIDS_RETRY_HOST_TEST
    SafePCKidsCredential* HostTestCredential();
#endif

    // IUnknown
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** ppv) override;
    ULONG STDMETHODCALLTYPE AddRef() override;
    ULONG STDMETHODCALLTYPE Release() override;

    // ICredentialProvider
    HRESULT STDMETHODCALLTYPE SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, DWORD dwFlags) override;
    HRESULT STDMETHODCALLTYPE SetSerialization(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs) override;
    HRESULT STDMETHODCALLTYPE Advise(ICredentialProviderEvents* pcpe, UINT_PTR upAdviseContext) override;
    HRESULT STDMETHODCALLTYPE UnAdvise() override;
    HRESULT STDMETHODCALLTYPE GetFieldDescriptorCount(DWORD* pdwCount) override;
    HRESULT STDMETHODCALLTYPE GetFieldDescriptorAt(DWORD dwIndex, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd) override;
    HRESULT STDMETHODCALLTYPE GetCredentialCount(DWORD* pdwCount, DWORD* pdwDefault, BOOL* pbAutoLogonWithDefault) override;
    HRESULT STDMETHODCALLTYPE GetCredentialAt(DWORD dwIndex, ICredentialProviderCredential** ppcpc) override;

    // ICredentialProviderSetUserArray
    HRESULT STDMETHODCALLTYPE SetUserArray(ICredentialProviderUserArray* users) override;
};
