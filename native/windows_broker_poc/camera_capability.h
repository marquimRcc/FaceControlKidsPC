// P0-13: Media Foundation camera CAPABILITY diagnostic from broker process.
// Enumerating a camera is NOT proof of a live person, a trustworthy frame,
// webcam access from LogonUI, or permission to unlock Windows.
// This file contains no image capture, biometric processing or persistence.
#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mferror.h>
#include <objbase.h>
#include <string>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mfuuid.lib")

namespace facekids_camera {

enum class Capability {
    Unknown,
    NoCamera,
    EnumeratedOnly,
    MediaFoundationUnavailable
};

struct DeviceInventory {
    Capability capability=Capability::Unknown;
    unsigned int device_count=0;
    HRESULT code=E_FAIL;

    // IMPORTANT: NEVER infer identity or liveness from device presence.
    bool usable_for_authentication() const { return false; }
};

inline const char* describe(Capability state) {
    switch (state) {
        case Capability::NoCamera: return "NO_CAMERA";
        case Capability::EnumeratedOnly: return "CAMERA_ENUMERATED_NOT_VERIFIED";
        case Capability::MediaFoundationUnavailable: return "MF_UNAVAILABLE";
        default: return "UNKNOWN";
    }
}

// Uses the broker process's actual security token and session (SCM test
// exercises LocalSystem); no child-supplied counts, camera index or SID.
// Does not open a camera, acquire image frames or write user data.
inline DeviceInventory enumerate() {
    DeviceInventory result;
    HRESULT co=CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(co)) {
        result.capability=Capability::MediaFoundationUnavailable;
        result.code=co;
        return result;
    }
    HRESULT started=MFStartup(MF_VERSION);
    if (FAILED(started)) {
        result.capability=Capability::MediaFoundationUnavailable;
        result.code=started;
        CoUninitialize();
        return result;
    }
    IMFAttributes* attrs=nullptr;
    IMFActivate** cameras=nullptr;
    UINT32 count=0;
    HRESULT hr=MFCreateAttributes(&attrs, 1);
    if (SUCCEEDED(hr))
        hr=attrs->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,
                          MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
    if (SUCCEEDED(hr)) hr=MFEnumDeviceSources(attrs, &cameras, &count);
    if (SUCCEEDED(hr)) {
        result.device_count=count;
        result.capability=(count==0) ? Capability::NoCamera : Capability::EnumeratedOnly;
    } else {
        result.capability=Capability::MediaFoundationUnavailable;
    }
    result.code=hr;
    if (cameras) {
        for (UINT32 i=0;i<count;++i) {
            if (cameras[i]) cameras[i]->Release();
        }
        CoTaskMemFree(cameras);
    }
    if (attrs) attrs->Release();
    MFShutdown();
    CoUninitialize();
    return result;
}

inline bool self_test() {
    DeviceInventory inventory;
    if (inventory.usable_for_authentication()) return false;
    inventory.capability=Capability::EnumeratedOnly;
    inventory.device_count=4;
    if (inventory.usable_for_authentication()) return false;
    inventory.capability=Capability::NoCamera;
    inventory.device_count=0;
    if (inventory.usable_for_authentication()) return false;
    inventory.capability=Capability::MediaFoundationUnavailable;
    if (inventory.usable_for_authentication()) return false;
    return std::string(describe(Capability::EnumeratedOnly)) ==
           "CAMERA_ENUMERATED_NOT_VERIFIED";
}

} // namespace facekids_camera
