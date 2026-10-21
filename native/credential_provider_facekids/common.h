#pragma once
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <credentialprovider.h>
#include <ntsecapi.h>
#include <objbase.h>
#include <sddl.h>
#include <string>
#include <vector>
#include <cwchar>

// CLSID: {FAC0D042-3DD0-4A8C-9F18-440C44330C20}
static const CLSID CLSID_FaceKidsProvider = {
    0xfac0d042, 0x3dd0, 0x4a8c, { 0x9f, 0x18, 0x44, 0x0c, 0x44, 0x33, 0x0c, 0x20 }
};

enum FIELD_ID {
    FIELD_TITLE = 0,
    FIELD_STATUS = 1,
    FIELD_RETRY_BUTTON = 2,
    FIELD_COUNT = 3
};

static HRESULT clone_text(PCWSTR src, PWSTR* out) {
    if (!out) return E_POINTER;
    *out = nullptr;
    if (!src) return S_OK;
    const size_t size = (wcslen(src) + 1) * sizeof(WCHAR);
    *out = static_cast<PWSTR>(CoTaskMemAlloc(size));
    if (!*out) return E_OUTOFMEMORY;
    memcpy(*out, src, size);
    return S_OK;
}
