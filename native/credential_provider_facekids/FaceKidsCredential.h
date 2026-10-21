#pragma once
#include "common.h"
#include "FaceKidsPipeClient.h"
#include "FaceKidsSerialization.h"

class FaceKidsProvider;

class FaceKidsCredential final : public ICredentialProviderCredential2 {
private:
    volatile LONG m_cRef = 1;
    FaceKidsProvider* m_pProvider = nullptr;
    ICredentialProviderCredentialEvents* m_pEvents = nullptr;
    std::wstring m_boundSid;
    std::wstring m_statusText;
    AuthResult m_lastAuth;
    CRITICAL_SECTION m_cs;
    volatile bool m_isAuthenticating = false;

public:
    FaceKidsCredential(FaceKidsProvider* pProvider = nullptr);
    ~FaceKidsCredential();

    void SetProvider(FaceKidsProvider* pProvider) { m_pProvider = pProvider; }
    void BindSid(const std::wstring& sid) { m_boundSid = sid; }
    void TriggerAsyncAuth();
    void PerformAuthentication();

    // IUnknown
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** ppv) override;
    ULONG STDMETHODCALLTYPE AddRef() override;
    ULONG STDMETHODCALLTYPE Release() override;

    // ICredentialProviderCredential
    HRESULT STDMETHODCALLTYPE Advise(ICredentialProviderCredentialEvents* pcpce) override;
    HRESULT STDMETHODCALLTYPE UnAdvise() override;
    HRESULT STDMETHODCALLTYPE SetSelected(BOOL* pbAutoLogon) override;
    HRESULT STDMETHODCALLTYPE SetDeselected() override;
    HRESULT STDMETHODCALLTYPE GetFieldState(DWORD dwFieldID, CREDENTIAL_PROVIDER_FIELD_STATE* pcpfs, CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* pcpfis) override;
    HRESULT STDMETHODCALLTYPE GetStringValue(DWORD dwFieldID, PWSTR* ppsz) override;
    HRESULT STDMETHODCALLTYPE GetBitmapValue(DWORD dwFieldID, HBITMAP* phbmp) override;
    HRESULT STDMETHODCALLTYPE GetCheckboxValue(DWORD dwFieldID, BOOL* pbChecked, PWSTR* ppszLabel) override;
    HRESULT STDMETHODCALLTYPE GetSubmitButtonValue(DWORD dwFieldID, DWORD* pdwAdjacentTo) override;
    HRESULT STDMETHODCALLTYPE GetComboBoxValueCount(DWORD dwFieldID, DWORD* pcItems, DWORD* pdwSelectedItem) override;
    HRESULT STDMETHODCALLTYPE GetComboBoxValueAt(DWORD dwFieldID, DWORD dwItem, PWSTR* ppszItem) override;
    HRESULT STDMETHODCALLTYPE SetStringValue(DWORD dwFieldID, PCWSTR psz) override;
    HRESULT STDMETHODCALLTYPE SetCheckboxValue(DWORD dwFieldID, BOOL bChecked) override;
    HRESULT STDMETHODCALLTYPE SetComboBoxSelectedValue(DWORD dwFieldID, DWORD dwSelectedItem) override;
    HRESULT STDMETHODCALLTYPE CommandLinkClicked(DWORD dwFieldID) override;
    HRESULT STDMETHODCALLTYPE GetSerialization(CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* pcpgsr, CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs, PWSTR* ppszOptionalStatusText, CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) override;
    HRESULT STDMETHODCALLTYPE ReportResult(NTSTATUS ntsStatus, NTSTATUS ntsSubstatus, PWSTR* ppszOptionalStatusText, CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) override;

    // ICredentialProviderCredential2
    HRESULT STDMETHODCALLTYPE GetUserSid(PWSTR* ppszSid) override;
};
