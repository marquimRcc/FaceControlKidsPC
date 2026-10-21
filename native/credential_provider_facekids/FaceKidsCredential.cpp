#include "FaceKidsCredential.h"
#include <process.h>

extern volatile LONG g_cObjects;

FaceKidsCredential::FaceKidsCredential() {
    InterlockedIncrement(&g_cObjects);
    InitializeCriticalSection(&m_cs);
    m_statusText = L"Olhe para a webcam para desbloquear...";
}

FaceKidsCredential::~FaceKidsCredential() {
    DeleteCriticalSection(&m_cs);
    InterlockedDecrement(&g_cObjects);
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::QueryInterface(REFIID riid, void** ppv) {
    if (!ppv) return E_POINTER;
    *ppv = nullptr;
    if (riid == IID_IUnknown || riid == IID_ICredentialProviderCredential) {
        *ppv = static_cast<ICredentialProviderCredential*>(this);
        AddRef();
        return S_OK;
    }
    if (riid == IID_ICredentialProviderCredential2) {
        *ppv = static_cast<ICredentialProviderCredential2*>(this);
        AddRef();
        return S_OK;
    }
    return E_NOINTERFACE;
}

ULONG STDMETHODCALLTYPE FaceKidsCredential::AddRef() {
    return static_cast<ULONG>(InterlockedIncrement(&m_cRef));
}

ULONG STDMETHODCALLTYPE FaceKidsCredential::Release() {
    LONG n = InterlockedDecrement(&m_cRef);
    if (n == 0) delete this;
    return static_cast<ULONG>(n);
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::Advise(ICredentialProviderCredentialEvents* pcpce) {
    EnterCriticalSection(&m_cs);
    m_pEvents = pcpce;
    if (m_pEvents) m_pEvents->AddRef();
    LeaveCriticalSection(&m_cs);
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::UnAdvise() {
    EnterCriticalSection(&m_cs);
    if (m_pEvents) {
        m_pEvents->Release();
        m_pEvents = nullptr;
    }
    LeaveCriticalSection(&m_cs);
    return S_OK;
}

static unsigned __stdcall AuthThreadProc(void* param) {
    auto* cred = static_cast<FaceKidsCredential*>(param);
    cred->PerformAuthentication();
    cred->Release();
    return 0;
}

void FaceKidsCredential::TriggerAsyncAuth() {
    EnterCriticalSection(&m_cs);
    m_statusText = L"Identificando... Olhe para a webcam.";
    ICredentialProviderCredentialEvents* events = m_pEvents;
    if (events) events->AddRef();
    LeaveCriticalSection(&m_cs);

    if (events) {
        events->OnCreatingWindow(nullptr);
        events->Release();
    }

    AddRef();
    uintptr_t hThread = _beginthreadex(nullptr, 0, AuthThreadProc, this, 0, nullptr);
    if (hThread) {
        CloseHandle(reinterpret_cast<HANDLE>(hThread));
    } else {
        Release();
    }
}

void FaceKidsCredential::PerformAuthentication() {
    AuthResult auth = FaceKidsPipeClient::RequestAuthentication();

    EnterCriticalSection(&m_cs);
    m_lastAuth = auth;
    if (auth.success) {
        if (!auth.childName.empty()) {
            m_statusText = L"Ola, " + auth.childName + L"! Desbloqueando...";
        } else {
            m_statusText = L"Rosto reconhecido! Desbloqueando...";
        }
    } else {
        m_statusText = auth.message.empty() ? L"Rosto nao reconhecido. Tente novamente." : auth.message;
    }

    ICredentialProviderCredentialEvents* events = m_pEvents;
    if (events) events->AddRef();
    LeaveCriticalSection(&m_cs);

    if (events) {
        events->OnCreatingWindow(nullptr);
        events->Release();
    }
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::SetSelected(BOOL* pbAutoLogon) {
    if (!pbAutoLogon) return E_POINTER;
    *pbAutoLogon = FALSE;
    TriggerAsyncAuth();
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::SetDeselected() {
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::GetFieldState(
    DWORD dwFieldID,
    CREDENTIAL_PROVIDER_FIELD_STATE* pcpfs,
    CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* pcpfis) {
    if (!pcpfs || !pcpfis) return E_POINTER;
    if (dwFieldID >= FIELD_COUNT) return E_INVALIDARG;

    *pcpfs = CPFS_DISPLAY_IN_SELECTED_TILE;
    *pcpfis = CPFIS_NONE;

    if (dwFieldID == FIELD_RETRY_BUTTON) {
        *pcpfis = CPFIS_FOCUSED;
    }
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::GetStringValue(DWORD dwFieldID, PWSTR* ppsz) {
    if (!ppsz) return E_POINTER;
    *ppsz = nullptr;

    EnterCriticalSection(&m_cs);
    HRESULT hr = S_OK;
    if (dwFieldID == FIELD_TITLE) {
        hr = clone_text(L"FaceKids - Desbloqueio Facial", ppsz);
    } else if (dwFieldID == FIELD_STATUS) {
        hr = clone_text(m_statusText.c_str(), ppsz);
    } else if (dwFieldID == FIELD_RETRY_BUTTON) {
        hr = clone_text(L"Verificar Rosto Novamente", ppsz);
    } else {
        hr = E_INVALIDARG;
    }
    LeaveCriticalSection(&m_cs);
    return hr;
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::GetBitmapValue(DWORD, HBITMAP*) { return E_NOTIMPL; }
HRESULT STDMETHODCALLTYPE FaceKidsCredential::GetCheckboxValue(DWORD, BOOL*, PWSTR*) { return E_NOTIMPL; }
HRESULT STDMETHODCALLTYPE FaceKidsCredential::GetSubmitButtonValue(DWORD, DWORD*) { return E_NOTIMPL; }
HRESULT STDMETHODCALLTYPE FaceKidsCredential::GetComboBoxValueCount(DWORD, DWORD*, DWORD*) { return E_NOTIMPL; }
HRESULT STDMETHODCALLTYPE FaceKidsCredential::GetComboBoxValueAt(DWORD, DWORD, PWSTR*) { return E_NOTIMPL; }
HRESULT STDMETHODCALLTYPE FaceKidsCredential::SetStringValue(DWORD, PCWSTR) { return E_NOTIMPL; }
HRESULT STDMETHODCALLTYPE FaceKidsCredential::SetCheckboxValue(DWORD, BOOL) { return E_NOTIMPL; }
HRESULT STDMETHODCALLTYPE FaceKidsCredential::SetComboBoxSelectedValue(DWORD, DWORD) { return E_NOTIMPL; }

HRESULT STDMETHODCALLTYPE FaceKidsCredential::CommandLinkClicked(DWORD dwFieldID) {
    if (dwFieldID == FIELD_RETRY_BUTTON) {
        TriggerAsyncAuth();
        return S_OK;
    }
    return E_NOTIMPL;
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::GetSerialization(
    CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* pcpgsr,
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs,
    PWSTR* ppszOptionalStatusText,
    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) {
    if (!pcpgsr || !pcpcs || !ppszOptionalStatusText || !pcpsiOptionalStatusIcon) return E_POINTER;

    *pcpgsr = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
    *pcpcs = {};
    *ppszOptionalStatusText = nullptr;
    *pcpsiOptionalStatusIcon = CPSI_NONE;

    EnterCriticalSection(&m_cs);
    const bool ok = m_lastAuth.success;
    const std::wstring user = m_lastAuth.user;
    const std::wstring pass = m_lastAuth.password;
    LeaveCriticalSection(&m_cs);

    if (ok && !user.empty() && !pass.empty()) {
        HRESULT hr = FaceKidsSerialization::SerializeKerbInteractiveLogon(
            L".",
            user.c_str(),
            pass.c_str(),
            &pcpcs->rgbSerialization,
            &pcpcs->cbSerialization,
            &pcpcs->ulAuthenticationPackage
        );

        if (SUCCEEDED(hr)) {
            pcpcs->clsidCredentialProvider = CLSID_FaceKidsProvider;
            *pcpgsr = CPGSR_RETURN_CREDENTIAL_FINISHED;
            clone_text(L"Acesso Facial Autorizado!", ppszOptionalStatusText);
            *pcpsiOptionalStatusIcon = CPSI_SUCCESS;
            return S_OK;
        }
    }

    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::ReportResult(
    NTSTATUS, NTSTATUS, PWSTR* ppszOptionalStatusText, CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) {
    if (ppszOptionalStatusText) *ppszOptionalStatusText = nullptr;
    if (pcpsiOptionalStatusIcon) *pcpsiOptionalStatusIcon = CPSI_NONE;
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::GetUserSid(PWSTR* ppszSid) {
    if (!ppszSid) return E_POINTER;
    *ppszSid = nullptr;
    return m_boundSid.empty() ? E_UNEXPECTED : clone_text(m_boundSid.c_str(), ppszSid);
}
