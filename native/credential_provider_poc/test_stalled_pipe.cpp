// Regression: a stalled named-pipe server must not freeze the CP client.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <thread>
#include <cstdio>
#include "precheck_client.h"

int wmain() {
    constexpr wchar_t pipeName[]=LR"(\\.\pipe\FaceKidsBrokerPoc-v1)";
    HANDLE server=CreateNamedPipeW(pipeName, PIPE_ACCESS_DUPLEX,
        PIPE_TYPE_MESSAGE|PIPE_READMODE_MESSAGE|PIPE_WAIT|PIPE_REJECT_REMOTE_CLIENTS,
        1, 256, 256, 0, nullptr);
    if (server==INVALID_HANDLE_VALUE) return 2;
    std::thread worker([&]() {
        BOOL connected=ConnectNamedPipe(server, nullptr);
        if (!connected && GetLastError()==ERROR_PIPE_CONNECTED) connected=TRUE;
        if (connected) {
            char bytes[32]={};
            DWORD received=0;
            ReadFile(server, bytes, sizeof(bytes), &received, nullptr);
            Sleep(2500); // deliberately never reply before client's deadline
        }
        DisconnectNamedPipe(server);
        CloseHandle(server);
    });
    Sleep(50);
    const ULONGLONG start=GetTickCount64();
    const auto result=facekids_cp_client::request(7,1);
    const ULONGLONG elapsed=GetTickCount64()-start;
    worker.join();
    if (result!=facekids_cp_client::Precheck::Denied || elapsed>2000) {
        std::printf("FAIL: stalled server took %llu ms\n",
                    static_cast<unsigned long long>(elapsed));
        return 3;
    }
    std::printf("PASS: stalled diagnostic pipe denied in %llu ms\n",
                static_cast<unsigned long long>(elapsed));
    return 0;
}
