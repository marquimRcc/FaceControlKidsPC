// P0-1B Windows Media Foundation webcam diagnostic for an already-open session.
// No credentials, no Credential Provider installation, no saved photos or video.
// The user manually presses Win+L while this tool collects numeric statistics.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <wtsapi32.h>
#include <cstdio>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <chrono>
#include <string>
#include <algorithm>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mfreadwrite.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "wtsapi32.lib")

template<class T>
static void drop(T*& ptr) { if (ptr) { ptr->Release(); ptr = nullptr; } }

static std::string session_state() {
    LPWSTR memory = nullptr;
    DWORD length = 0;
    std::string result = "unknown";
    // WTSSessionInfoEx reports lock state for the current interactive session.
    if (WTSQuerySessionInformationW(WTS_CURRENT_SERVER_HANDLE, WTS_CURRENT_SESSION,
                                   WTSSessionInfoEx, &memory, &length) && memory) {
        if (length >= sizeof(WTSINFOEXW)) {
            const WTSINFOEXW* info = reinterpret_cast<const WTSINFOEXW*>(memory);
            if (info->Level == 1) {
                const auto& level = info->Data.WTSInfoExLevel1;
                if (level.SessionState != WTSActive) result = "disconnected";
                else if (level.SessionFlags == 0) result = "locked";
                else if (level.SessionFlags == 1) result = "active";
            }
        }
    }
    if (memory) WTSFreeMemory(memory);
    return result;
}

static bool sample_statistics(IMFSample* sample, double& mean, double& stdev) {
    IMFMediaBuffer* buffer = nullptr;
    if (FAILED(sample->ConvertToContiguousBuffer(&buffer)) || !buffer) return false;
    BYTE* data = nullptr;
    DWORD maximum = 0, length = 0;
    bool success = false;
    if (SUCCEEDED(buffer->Lock(&data, &maximum, &length))) {
        // RGB32: B,G,R,X, sampling every 32nd pixel to avoid copying frames.
        double sum = 0.0, sumsq = 0.0;
        size_t count = 0;
        for (size_t i = 0; i + 2 < length; i += 128) {
            const double y = (static_cast<double>(data[i]) +
                              static_cast<double>(data[i + 1]) +
                              static_cast<double>(data[i + 2])) / 3.0;
            sum += y;
            sumsq += y * y;
            ++count;
        }
        if (count > 50) {
            mean = sum / static_cast<double>(count);
            stdev = std::sqrt(std::max(0.0, sumsq / count - mean * mean));
            success = true;
        }
        buffer->Unlock();
    }
    drop(buffer);
    return success;
}

int wmain(int argc, wchar_t** argv) {
    int duration = 120, camera_index = 0;
    if (argc > 1) duration = _wtoi(argv[1]);
    if (argc > 2) camera_index = _wtoi(argv[2]);
    if (argc > 3 || duration < 10 || duration > 600 || camera_index < 0) {
        std::puts("Usage: FaceKidsMFProbe.exe [duration: 10..600 seconds] [camera index >= 0]");
        return 2;
    }

    HRESULT co = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(co)) return 3;
    HRESULT started = MFStartup(MF_VERSION, MFSTARTUP_LITE);
    if (FAILED(started)) { CoUninitialize(); return 4; }

    IMFAttributes* attrs = nullptr;
    IMFActivate** devices = nullptr;
    UINT32 device_count = 0;
    IMFMediaSource* media = nullptr;
    IMFSourceReader* reader = nullptr;
    IMFMediaType* format = nullptr;
    HRESULT hr = MFCreateAttributes(&attrs, 1);
    if (SUCCEEDED(hr)) hr = attrs->SetGUID(
        MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE, MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
    if (SUCCEEDED(hr)) hr = MFEnumDeviceSources(attrs, &devices, &device_count);
    if (SUCCEEDED(hr) && static_cast<UINT32>(camera_index) >= device_count) {
        std::printf("Camera index %d unavailable; detected %u cameras.\n", camera_index, device_count);
        hr = E_INVALIDARG;
    }
    if (SUCCEEDED(hr)) hr = devices[camera_index]->ActivateObject(IID_PPV_ARGS(&media));
    if (SUCCEEDED(hr)) hr = MFCreateSourceReaderFromMediaSource(media, nullptr, &reader);
    if (SUCCEEDED(hr)) hr = MFCreateMediaType(&format);
    if (SUCCEEDED(hr)) hr = format->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
    if (SUCCEEDED(hr)) hr = format->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_RGB32);
    // The source reader can convert the camera's native format to RGB32.
    if (SUCCEEDED(hr)) hr = reader->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, nullptr, format);

    int exit_code = 0;
    if (FAILED(hr)) {
        std::printf("Cannot initialize Media Foundation camera or RGB32 conversion: 0x%08lx\n",
                    static_cast<unsigned long>(hr));
        exit_code = 5;
    } else {
        std::ofstream csv("FaceKids-MediaFoundation-WinL.csv", std::ios::trunc);
        if (!csv) {
            std::puts("Cannot write FaceKids-MediaFoundation-WinL.csv in this directory.");
            exit_code = 6;
        } else {
            csv << "elapsed_seconds,session,capture_ok,frame_nonuniform,brightness_mean,brightness_stddev,read_hresult\n";
            csv.flush();
            std::puts("FaceKids Media Foundation diagnostic started.");
            std::puts("Press Win+L now; keep Windows locked 30-60 seconds; unlock normally.");
            std::puts("Only brightness statistics are logged. No images are saved.");
            int locked = 0, good_locked = 0, active = 0;
            const auto start = std::chrono::steady_clock::now();
            for (int second = 0; second < duration; ++second) {
                auto tick = std::chrono::steady_clock::now();
                const double elapsed = std::chrono::duration<double>(tick - start).count();
                std::string session = session_state();
                DWORD actual_stream = 0, flags = 0;
                LONGLONG time = 0;
                IMFSample* frame = nullptr;
                HRESULT read = reader->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM, 0,
                                                  &actual_stream, &flags, &time, &frame);
                double mean = 0, stdev = 0;
                const bool ok = SUCCEEDED(read) && frame &&
                                !(flags & (MF_SOURCE_READERF_ENDOFSTREAM | MF_SOURCE_READERF_ERROR)) &&
                                sample_statistics(frame, mean, stdev);
                drop(frame);
                const bool nonuniform = ok && stdev >= 2.0;
                if (session == "locked") {
                    ++locked;
                    if (nonuniform) ++good_locked;
                }
                if (session == "active") ++active;
                csv << elapsed << ',' << session << ',' << int(ok) << ',' << int(nonuniform)
                    << ',' << mean << ',' << stdev << ','
                    << static_cast<unsigned long>(read) << '\n';
                csv.flush();
                if (second % 10 == 0)
                    std::printf("t=%ds state=%s frame=%s\n", second, session.c_str(), ok ? "yes" : "no");
                auto next = tick + std::chrono::seconds(1);
                auto now = std::chrono::steady_clock::now();
                if (next > now) Sleep(static_cast<DWORD>(
                    std::chrono::duration_cast<std::chrono::milliseconds>(next - now).count()));
            }
            std::printf("Locked samples: %d / nonuniform frames: %d / active samples: %d\n",
                        locked, good_locked, active);
            if (locked < 5) std::puts("INCONCLUSIVE: WTS did not report at least 5 locked samples.");
            else if (good_locked >= 3) std::puts("CAMERA_READS_DURING_LOCK: preliminary evidence only.");
            else std::puts("NO_USABLE_LOCKED_FRAMES: test backend/privacy/camera.");
            std::puts("Report: FaceKids-MediaFoundation-WinL.csv");
        }
    }
    drop(format);
    drop(reader);
    drop(media);
    if (devices) {
        for (UINT32 i = 0; i < device_count; ++i) drop(devices[i]);
        CoTaskMemFree(devices);
    }
    drop(attrs);
    MFShutdown();
    CoUninitialize();
    return exit_code;
}
