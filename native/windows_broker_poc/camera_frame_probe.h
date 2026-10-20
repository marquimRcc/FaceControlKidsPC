// P0-26: opt-in in-memory Media Foundation frame diagnostic.
// No frame bytes, images, vectors, identity or biometric data leave memory.
// This is NOT trusted liveness, face recognition or Windows authentication.
#pragma once
#include "camera_capability.h"
#include <mfreadwrite.h>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <algorithm>

#pragma comment(lib, "mfreadwrite.lib")

namespace facekids_frame {

enum class Status { FrameMeasured, NoCamera, CaptureUnavailable };

struct Result {
    Status status=Status::CaptureUnavailable;
    bool nonuniform=false;
    HRESULT hr=E_FAIL;
    // Diagnostic only: NEVER treat as valid facial evidence.
    bool authentication_allowed() const { return false; }
};

template<class T> inline void release(T*& pointer) {
    if(pointer) { pointer->Release(); pointer=nullptr; }
}

// RGB32/BGRA pixels; only a sparse brightness calculation is made.
// No raw pixels can be returned from this boundary.
inline bool check_frame(const unsigned char* pixels, size_t bytes, bool& nonuniform) {
    nonuniform=false;
    if(!pixels || bytes < 8192 || bytes%4!=0) return false;
    double sum=0, sumSquares=0;
    size_t samples=0;
    for(size_t i=0; i+3<bytes; i+=128) {
        const double lum=(double(pixels[i])+double(pixels[i+1])+
                          double(pixels[i+2]))/3.0;
        sum+=lum;
        sumSquares+=lum*lum;
        ++samples;
    }
    if(samples < 50) return false;
    const double mean=sum/double(samples);
    const double variance=std::max(0.0, sumSquares/double(samples)-mean*mean);
    nonuniform=std::sqrt(variance)>=2.0;
    return true;
}

inline bool self_test() {
    unsigned char rgb[16384]={};
    bool nonuniform=true;
    if(!check_frame(rgb,sizeof(rgb),nonuniform) || nonuniform) return false;
    for(size_t i=0;i<sizeof(rgb);i+=128) {
        rgb[i]=static_cast<unsigned char>(((i/128)%2)*200);
        rgb[i+1]=rgb[i];
        rgb[i+2]=rgb[i];
    }
    if(!check_frame(rgb,sizeof(rgb),nonuniform) || !nonuniform) return false;
    if(check_frame(nullptr,sizeof(rgb),nonuniform) ||
       check_frame(rgb, 120,nonuniform) ||
       check_frame(rgb,sizeof(rgb)-1,nonuniform)) return false;
    return !Result{}.authentication_allowed();
}

// EXPLICIT DIAGNOSTIC CLI only. Must NOT run on SCM startup, LogonUI,
// or any credential path. May block while a physical camera responds.
// No output file, frame dump, or biometric enrollment is produced.
inline Result capture_one_frame(unsigned int camera_index=0) {
    Result output;
    HRESULT co=CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if(FAILED(co)) { output.hr=co; return output; }
    HRESULT hr=MFStartup(MF_VERSION);
    if(FAILED(hr)) { output.hr=hr; CoUninitialize(); return output; }
    IMFAttributes* attrs=nullptr;
    IMFActivate** devices=nullptr;
    UINT32 count=0;
    IMFMediaSource* source=nullptr;
    IMFSourceReader* reader=nullptr;
    IMFMediaType* type=nullptr;
    IMFSample* sample=nullptr;
    IMFMediaBuffer* buffer=nullptr;
    hr=MFCreateAttributes(&attrs,1);
    if(SUCCEEDED(hr)) hr=attrs->SetGUID(
        MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,
        MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
    if(SUCCEEDED(hr)) hr=MFEnumDeviceSources(attrs,&devices,&count);
    if(SUCCEEDED(hr) && camera_index>=count) {
        output.status=Status::NoCamera;
        hr=HRESULT_FROM_WIN32(ERROR_NOT_FOUND);
    }
    if(SUCCEEDED(hr)) hr=devices[camera_index]->ActivateObject(IID_PPV_ARGS(&source));
    if(SUCCEEDED(hr)) hr=MFCreateSourceReaderFromMediaSource(source,nullptr,&reader);
    if(SUCCEEDED(hr)) hr=MFCreateMediaType(&type);
    if(SUCCEEDED(hr)) hr=type->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video);
    if(SUCCEEDED(hr)) hr=type->SetGUID(MF_MT_SUBTYPE,MFVideoFormat_RGB32);
    if(SUCCEEDED(hr)) hr=reader->SetCurrentMediaType(
        MF_SOURCE_READER_FIRST_VIDEO_STREAM,nullptr,type);
    if(SUCCEEDED(hr)) {
        DWORD stream=0, flags=0;
        LONGLONG timestamp=0;
        hr=reader->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,
                              &stream,&flags,&timestamp,&sample);
        if(SUCCEEDED(hr) && sample &&
            !(flags & (MF_SOURCE_READERF_ENDOFSTREAM|MF_SOURCE_READERF_ERROR))) {
            hr=sample->ConvertToContiguousBuffer(&buffer);
            if(SUCCEEDED(hr)) {
                unsigned char* bytes=nullptr;
                DWORD capacity=0,length=0;
                hr=buffer->Lock(&bytes,&capacity,&length);
                if(SUCCEEDED(hr)) {
                    bool nonuniform=false;
                    const bool valid=check_frame(bytes,length,nonuniform);
                    buffer->Unlock();
                    if(valid) {
                        output.status=Status::FrameMeasured;
                        output.nonuniform=nonuniform;
                    }
                }
            }
        }
    }
    output.hr=hr;
    release(buffer);
    release(sample);
    release(type);
    release(reader);
    release(source);
    if(devices) {
        for(UINT32 i=0;i<count;++i) release(devices[i]);
        CoTaskMemFree(devices);
    }
    release(attrs);
    MFShutdown();
    CoUninitialize();
    return output;
}

} // namespace facekids_frame
