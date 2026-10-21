#include "FaceKidsProvider.h"

extern volatile LONG g_cObjects;

FaceKidsProvider::FaceKidsProvider() : m_pCredential(new(std::nothrow) FaceKidsCredential()) {
    InterlockedIncrement(&g_cObjects);
    m_targetSid = ResolveTargetSid();
}

FaceKidsProvider::~FaceKidsProvider() {
    if (m_pCredential) {
        m_pCredential->Release();
        m_pCredential = nullptr;
    }
    InterlockedDecrement(&g_cObjects);
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

HRESULT STDMETHODCALLTYPE FaceKidsProvider::SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, DWORD) {
    if (cpus == CPUS_LOGON || cpus == CPUS_UNLOCK_WORKSTATION) {
        return S_OK;
    }
    return E_NOTIMPL;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::SetSerialization(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION*) {
    return E_NOTIMPL;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::Advise(ICredentialProviderEvents*, UINT_PTR) {
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::UnAdvise() {
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::SetUserArray(ICredentialProviderUserArray* users) {
    m_eligible = false;
    if (m_pCredential) m_pCredential->BindSid(L"");
    if (!users) return E_POINTER;

    if (m_targetSid.empty()) {
        m_targetSid = ResolveTargetSid();
    }
    if (m_targetSid.empty() || !m_pCredential) {
        return S_OK;
    }

    DWORD count = 0;
    if (FAILED(users->GetCount(&count))) return S_OK;

    for (DWORD i = 0; i < count; ++i) {
        ICredentialProviderUser* user = nullptr;
        if (FAILED(users->GetAt(i, &user)) || !user) continue;

        PWSTR pSid = nullptr;
        if (SUCCEEDED(user->GetSid(&pSid)) && pSid) {
            if (_wcsicmp(pSid, m_targetSid.c_str()) == 0) {
                m_pCredential->BindSid(pSid);
                m_eligible = true;
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
    *pdwDefault = CREDENTIAL_PROVIDER_NO_DEFAULT;
    *pbAutoLogonWithDefault = FALSE;
    return S_OK;
}

HRESULT STDMETHODCALLTYPE FaceKidsProvider::GetCredentialAt(DWORD dwIndex, ICredentialProviderCredential** ppcpc) {
    if (!ppcpc) return E_POINTER;
    *ppcpc = nullptr;
    if (dwIndex != 0 || !m_pCredential || !m_eligible) return E_INVALIDARG;
    return m_pCredential->QueryInterface(IID_ICredentialProviderCredential, reinterpret_cast<void**>(ppcpc));
}
