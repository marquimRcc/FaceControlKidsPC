#include "FaceKidsCredential.h"
#include "FaceKidsProvider.h"
#include <process.h>

extern volatile LONG g_cObjects;

FaceKidsCredential::FaceKidsCredential(FaceKidsProvider* pProvider) : m_pProvider(pProvider) {
    OutputDebugStringA("FACEKIDS_BOOT_RETRY_V1");
    InterlockedIncrement(&g_cObjects);
    InitializeCriticalSection(&m_cs);
    m_statusText = L"Olhe para a webcam para desbloquear...";
    LogCP(L"[FaceKidsCredential] Construtor");
}

FaceKidsCredential::~FaceKidsCredential() {
    DeleteCriticalSection(&m_cs);
    InterlockedDecrement(&g_cObjects);
    LogCP(L"[FaceKidsCredential] Destrutor");
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
    LogCP(L"[FaceKidsCredential] Advise");
    EnterCriticalSection(&m_cs);
    if (m_pEvents) m_pEvents->Release();
    m_pEvents = pcpce;
    if (m_pEvents) m_pEvents->AddRef();
    m_authEnabled = true;
    LeaveCriticalSection(&m_cs);

    // Dispara a autenticacao imediatamente assim que o tile e criado pelo LogonUI
    TriggerAsyncAuth();
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::UnAdvise() {
    LogCP(L"[FaceKidsCredential] UnAdvise");
    EnterCriticalSection(&m_cs);
    m_authEnabled = false;
    ++m_authGeneration;
    if (m_pEvents) {
        m_pEvents->Release();
        m_pEvents = nullptr;
    }
    LeaveCriticalSection(&m_cs);
    return S_OK;
}

void FaceKidsCredential::ResetAuthentication() {
    EnterCriticalSection(&m_cs);
    m_authEnabled = false;
    ++m_authGeneration;
    m_lastAuth = {};
    m_statusText = L"Olhe para a webcam para desbloquear...";
    LeaveCriticalSection(&m_cs);
}

static unsigned __stdcall AuthThreadProc(void* param) {
    auto* cred = static_cast<FaceKidsCredential*>(param);
    cred->PerformAuthentication();
    cred->Release();
    return 0;
}

void FaceKidsCredential::TriggerAsyncAuth() {
    EnterCriticalSection(&m_cs);
    if (!m_authEnabled || m_isAuthenticating || m_lastAuth.success) {
        LeaveCriticalSection(&m_cs);
        return;
    }
    m_isAuthenticating = true;
    m_statusText = L"Identificando... Olhe para a webcam.";
    ICredentialProviderCredentialEvents* events = m_pEvents;
    if (events) events->AddRef();
    AddRef();
    FaceKidsProvider* provider = m_pProvider;
    if (provider && !provider->TryAddRef()) provider = nullptr;
    m_workerProvider = provider;
    LeaveCriticalSection(&m_cs);

    LogCP(L"[FaceKidsCredential] TriggerAsyncAuth disparado");
    if (events) {
        events->SetFieldString(this, FIELD_STATUS, L"Identificando... Olhe para a webcam.");
        events->Release();
    }

    // Provider owns this credential. Hold it for the worker lifetime so an
    // in-flight request cannot call a raw pointer after LogonUI releases it.
    uintptr_t hThread = _beginthreadex(nullptr, 0, AuthThreadProc, this, 0, nullptr);
    if (hThread) {
        CloseHandle(reinterpret_cast<HANDLE>(hThread));
    } else {
        EnterCriticalSection(&m_cs);
        m_isAuthenticating = false;
        LeaveCriticalSection(&m_cs);
        if (provider) provider->Release();
        Release();
    }
}

void FaceKidsCredential::PerformAuthentication() {
    EnterCriticalSection(&m_cs);
    FaceKidsProvider* heldProvider = m_workerProvider;
    LeaveCriticalSection(&m_cs);
    for (;;) {
        EnterCriticalSection(&m_cs);
        if (!m_authEnabled || m_lastAuth.success) {
            m_isAuthenticating = false;
            LeaveCriticalSection(&m_cs);
            break;
        }
        const unsigned long generation = m_authGeneration;
        LeaveCriticalSection(&m_cs);

        AuthResult auth = FaceKidsPipeClient::RequestAuthentication();
        EnterCriticalSection(&m_cs);
        // A reply from the previous tile activation must not authorize a new
        // activation after switching sign-in options/users or locking again.
        if (!m_authEnabled || generation != m_authGeneration) {
            LeaveCriticalSection(&m_cs);
            continue;
        }
        m_lastAuth = auth;
        m_statusText = auth.success
            ? L"Ola, " + auth.childName + L"! Desbloqueando..."
            : (auth.message.empty() ? L"Olhe para a webcam. Tentando novamente..." : auth.message);
        const std::wstring statusText = m_statusText;
        ICredentialProviderCredentialEvents* events = m_pEvents;
        if (events) events->AddRef();
        LeaveCriticalSection(&m_cs);

        if (events) {
            events->SetFieldString(this, FIELD_STATUS, statusText.c_str());
            events->Release();
        }
        if (auth.success) {
            // NotifyAuthSuccess/eligible SID remain the only route to Windows
            // serialization. A retry never bypasses identity, quota or curfew.
            EnterCriticalSection(&m_cs);
            const bool stillActive = m_authEnabled && generation == m_authGeneration;
            LeaveCriticalSection(&m_cs);
            if (stillActive && heldProvider) heldProvider->NotifyAuthSuccess();
        } else {
            Sleep(1000); // Worker thread only, never the LogonUI UI thread.
        }
    }
    if (heldProvider) heldProvider->Release();
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::SetSelected(BOOL* pbAutoLogon) {
    LogCP(L"[FaceKidsCredential] SetSelected");
    if (!pbAutoLogon) return E_POINTER;
    EnterCriticalSection(&m_cs);
    m_authEnabled = true;
    const bool ready = m_lastAuth.success;
    LeaveCriticalSection(&m_cs);
    if (ready) {
        *pbAutoLogon = TRUE;
    } else {
        *pbAutoLogon = FALSE;
        TriggerAsyncAuth();
    }
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::SetDeselected() {
    LogCP(L"[FaceKidsCredential] SetDeselected");
    EnterCriticalSection(&m_cs);
    m_authEnabled = false;
    ++m_authGeneration;
    m_lastAuth = {};
    if (m_pProvider) m_pProvider->ResetAuth();
    LeaveCriticalSection(&m_cs);
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
    LogCP(L"[FaceKidsCredential] CommandLinkClicked: field=%lu", dwFieldID);
    if (dwFieldID == FIELD_RETRY_BUTTON) {
        EnterCriticalSection(&m_cs);
        m_lastAuth = {};
        // Do not clear m_isAuthenticating: a pending worker still owns it.
        ++m_authGeneration;
        m_authEnabled = true;
        LeaveCriticalSection(&m_cs);
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
    LogCP(L"[FaceKidsCredential] GetSerialization chamado pelo LogonUI");
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
        LogCP(L"[FaceKidsCredential] Empacotando credencial do usuario: %s", user.c_str());
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
            LogCP(L"[FaceKidsCredential] CPGSR_RETURN_CREDENTIAL_FINISHED entregue ao Windows!");
            return S_OK;
        } else {
            LogCP(L"[FaceKidsCredential] ERRO ao serializar credencial: 0x%lx", hr);
        }
    } else {
        LogCP(L"[FaceKidsCredential] GetSerialization chamado sem autenticacao previa (ok=%d)", ok);
    }

    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::ReportResult(
    NTSTATUS status, NTSTATUS subStatus, PWSTR* ppszOptionalStatusText, CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) {
    LogCP(L"[FaceKidsCredential] ReportResult: status=0x%lx, subStatus=0x%lx", (unsigned long)status, (unsigned long)subStatus);
    EnterCriticalSection(&m_cs);
    if (status != 0) {
        m_lastAuth = {};
        m_statusText = L"Falha na autenticacao do Windows. Clique para tentar novamente.";
    }
    LeaveCriticalSection(&m_cs);

    if (ppszOptionalStatusText) *ppszOptionalStatusText = nullptr;
    if (pcpsiOptionalStatusIcon) *pcpsiOptionalStatusIcon = (status == 0) ? CPSI_SUCCESS : CPSI_ERROR;
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsCredential::GetUserSid(PWSTR* ppszSid) {
    if (!ppszSid) return E_POINTER;
    *ppszSid = nullptr;
    return m_boundSid.empty() ? E_UNEXPECTED : clone_text(m_boundSid.c_str(), ppszSid);
}
