#include "FaceKidsProvider.h"
#include "FaceKidsCredential.h"

extern volatile LONG g_cObjects;

FaceKidsProvider::FaceKidsProvider() : m_pCredential(new(std::nothrow) FaceKidsCredential(this)) {
    InterlockedIncrement(&g_cObjects);
    InitializeCriticalSection(&m_cs);
    m_targetSid = ResolveTargetSid();
    LogCP(L"[FaceKidsProvider] Construtor: targetSid=%s", m_targetSid.c_str());
}

FaceKidsProvider::~FaceKidsProvider() {
    DeleteCriticalSection(&m_cs);
    if (m_pCredential) {
        m_pCredential->Release();
        m_pCredential = nullptr;
    }
    InterlockedDecrement(&g_cObjects);
    LogCP(L"[FaceKidsProvider] Destrutor");
}

std::wstring FaceKidsProvider::ResolveTargetSid() {
    // 1. Tentar ler do Registro se configurado
    WCHAR sidReg[256] = {};
    DWORD cbData = sizeof(sidReg);
    LONG rc = RegGetValueW(
        HKEY_LOCAL_MACHINE,
        L"SOFTWARE\\FaceControlKidsPC\\CredentialProvider",
        L"TargetUserSid",
        RRF_RT_REG_SZ,
        nullptr,
        sidReg,
        &cbData
    );
    if (rc == ERROR_SUCCESS && sidReg[0] != L'\0') {
        return sidReg;
    }

    // 2. Resolver dinamicamente pelo nome da conta 'Filhos'
    BYTE sidBuffer[SECURITY_MAX_SID_SIZE] = {};
    DWORD sidSize = sizeof(sidBuffer);
    WCHAR domainBuffer[256] = {};
    DWORD domainSize = 256;
    SID_NAME_USE use;
    if (LookupAccountNameW(nullptr, L"Filhos", reinterpret_cast<PSID>(sidBuffer), &sidSize, domainBuffer, &domainSize, &use)) {
        LPWSTR pStrSid = nullptr;
        if (ConvertSidToStringSidW(reinterpret_cast<PSID>(sidBuffer), &pStrSid)) {
            std::wstring res(pStrSid);
            LocalFree(pStrSid);
            return res;
        }
    }
    return L"";
}

bool FaceKidsProvider::IsAutoLogonReady() const {
    return m_readyToAutoLogon;
}

void FaceKidsProvider::NotifyAuthSuccess() {
    LogCP(L"[FaceKidsProvider] NotifyAuthSuccess recebido da credencial!");
    EnterCriticalSection(&m_cs);
    m_readyToAutoLogon = true;
    ICredentialProviderEvents* pEvents = m_pEvents;
    UINT_PTR context = m_upAdviseContext;
    if (pEvents) pEvents->AddRef();
    LeaveCriticalSection(&m_cs);

    if (pEvents) {
        LogCP(L"[FaceKidsProvider] Disparando CredentialsChanged para o LogonUI (context=%llu)...", (unsigned long long)context);
        pEvents->CredentialsChanged(context);
        pEvents->Release();
    } else {
        LogCP(L"[FaceKidsProvider] AVISO: m_pEvents e nulo em NotifyAuthSuccess");
    }
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::QueryInterface(REFIID riid, void** ppv) {
    if (!ppv) return E_POINTER;
    *ppv = nullptr;
    if (riid == IID_IUnknown || riid == IID_ICredentialProvider) {
        *ppv = static_cast<ICredentialProvider*>(this);
        AddRef();
        return S_OK;
    }
    if (riid == IID_ICredentialProviderSetUserArray) {
        *ppv = static_cast<ICredentialProviderSetUserArray*>(this);
        AddRef();
        return S_OK;
    }
    return E_NOINTERFACE;
}

ULONG STDMETHODCALLTYPE FaceKidsProvider::AddRef() {
    return static_cast<ULONG>(InterlockedIncrement(&m_cRef));
}

ULONG STDMETHODCALLTYPE FaceKidsProvider::Release() {
    LONG n = InterlockedDecrement(&m_cRef);
    if (n == 0) delete this;
    return static_cast<ULONG>(n);
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, DWORD dwFlags) {
    LogCP(L"[FaceKidsProvider] SetUsageScenario: cpus=%d, flags=0x%x", cpus, dwFlags);
    if (cpus == CPUS_LOGON || cpus == CPUS_UNLOCK_WORKSTATION) {
        return S_OK;
    }
    return E_NOTIMPL;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::SetSerialization(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION*) {
    return E_NOTIMPL;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::Advise(ICredentialProviderEvents* pcpe, UINT_PTR upAdviseContext) {
    LogCP(L"[FaceKidsProvider] Advise: pcpe=%p, context=%llu", pcpe, (unsigned long long)upAdviseContext);
    EnterCriticalSection(&m_cs);
    m_pEvents = pcpe;
    if (m_pEvents) m_pEvents->AddRef();
    m_upAdviseContext = upAdviseContext;
    m_readyToAutoLogon = false;
    LeaveCriticalSection(&m_cs);
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::UnAdvise() {
    LogCP(L"[FaceKidsProvider] UnAdvise");
    EnterCriticalSection(&m_cs);
    if (m_pEvents) {
        m_pEvents->Release();
        m_pEvents = nullptr;
    }
    m_upAdviseContext = 0;
    m_readyToAutoLogon = false;
    LeaveCriticalSection(&m_cs);
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::SetUserArray(ICredentialProviderUserArray* users) {
    m_eligible = false;
    if (m_pCredential) m_pCredential->BindSid(L"");
    if (!users) {
        LogCP(L"[FaceKidsProvider] SetUserArray: users is null");
        return E_POINTER;
    }

    if (m_targetSid.empty()) {
        m_targetSid = ResolveTargetSid();
    }

    DWORD count = 0;
    if (FAILED(users->GetCount(&count))) {
        LogCP(L"[FaceKidsProvider] SetUserArray: GetCount failed");
        return S_OK;
    }

    LogCP(L"[FaceKidsProvider] SetUserArray: count=%d, targetSid=%s", count, m_targetSid.c_str());

    for (DWORD i = 0; i < count; ++i) {
        ICredentialProviderUser* user = nullptr;
        if (FAILED(users->GetAt(i, &user)) || !user) continue;

        PWSTR pSid = nullptr;
        if (SUCCEEDED(user->GetSid(&pSid)) && pSid) {
            LogCP(L"     - User[%d] SID: %s", i, pSid);
            if (_wcsicmp(pSid, m_targetSid.c_str()) == 0) {
                m_pCredential->BindSid(pSid);
                m_eligible = true;
                LogCP(L"     ===> MATCH COM A CONTA FILHOS!");
            }
            CoTaskMemFree(pSid);
        }
        user->Release();
        if (m_eligible) break;
    }
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::GetFieldDescriptorCount(DWORD* pdwCount) {
    if (!pdwCount) return E_POINTER;
    *pdwCount = FIELD_COUNT;
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::GetFieldDescriptorAt(DWORD dwIndex, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd) {
    if (!ppcpfd) return E_POINTER;
    *ppcpfd = nullptr;
    if (dwIndex >= FIELD_COUNT) return E_INVALIDARG;

    auto* desc = static_cast<CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR*>(
        CoTaskMemAlloc(sizeof(CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR))
    );
    if (!desc) return E_OUTOFMEMORY;
    ZeroMemory(desc, sizeof(*desc));

    desc->dwFieldID = dwIndex;
    if (dwIndex == FIELD_TITLE) {
        desc->cpft = CPFT_LARGE_TEXT;
        clone_text(L"FaceKids", &desc->pszLabel);
    } else if (dwIndex == FIELD_STATUS) {
        desc->cpft = CPFT_SMALL_TEXT;
        clone_text(L"Status", &desc->pszLabel);
    } else if (dwIndex == FIELD_RETRY_BUTTON) {
        desc->cpft = CPFT_COMMAND_LINK;
        clone_text(L"Verificar Rosto Novamente", &desc->pszLabel);
    }

    *ppcpfd = desc;
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::GetCredentialCount(DWORD* pdwCount, DWORD* pdwDefault, BOOL* pbAutoLogonWithDefault) {
    if (!pdwCount || !pdwDefault || !pbAutoLogonWithDefault) return E_POINTER;
    *pdwCount = (m_pCredential && m_eligible) ? 1 : 0;

    EnterCriticalSection(&m_cs);
    const bool autoLogon = m_readyToAutoLogon && m_eligible;
    LeaveCriticalSection(&m_cs);

    if (autoLogon) {
        *pdwDefault = 0;
        *pbAutoLogonWithDefault = TRUE;
        LogCP(L"[FaceKidsProvider] GetCredentialCount: AutoLogon ativado para tile 0!");
    } else {
        *pdwDefault = m_eligible ? 0 : CREDENTIAL_PROVIDER_NO_DEFAULT;
        *pbAutoLogonWithDefault = FALSE;
        LogCP(L"[FaceKidsProvider] GetCredentialCount: %d (m_eligible=%d, default=%d)", *pdwCount, m_eligible, *pdwDefault);
    }
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::GetCredentialAt(DWORD dwIndex, ICredentialProviderCredential** ppcpc) {
    LogCP(L"[FaceKidsProvider] GetCredentialAt: index=%d", dwIndex);
    if (!ppcpc) return E_POINTER;
    *ppcpc = nullptr;
    if (dwIndex != 0 || !m_pCredential || !m_eligible) return E_INVALIDARG;
    return m_pCredential->QueryInterface(IID_ICredentialProviderCredential, reinterpret_cast<void**>(ppcpc));
}
