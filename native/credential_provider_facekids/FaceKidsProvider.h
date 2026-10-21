#pragma once
#include "common.h"
#include "FaceKidsCredential.h"

class FaceKidsProvider final : public ICredentialProvider, public ICredentialProviderSetUserArray {
private:
    volatile LONG m_cRef = 1;
    FaceKidsCredential* m_pCredential = nullptr;
    bool m_eligible = false;
    std::wstring m_targetSid;

    std::wstring ResolveTargetSid();

public:
    FaceKidsProvider();
    ~FaceKidsProvider();

    bool IsValid() const { return m_pCredential != nullptr; }

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
