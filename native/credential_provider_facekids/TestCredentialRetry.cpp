// Isolated host: exercises the REAL credential worker with a fake local pipe.
// No registration, account change, Windows logon, webcam or biometric access.
#include "FaceKidsCredential.h"
#include "FaceKidsProvider.h"
#include <atomic>
#include <cstdlib>
#include <ctime>
#include <iostream>

volatile LONG g_cObjects = 0;

struct Server {
    HANDLE ready = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    HANDLE received = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    HANDLE releaseReply = CreateEventW(nullptr, TRUE, TRUE, nullptr);
    int replies = 2;
    std::atomic<int> requests{0};
};

static DWORD WINAPI Serve(LPVOID context) {
    auto& server = *static_cast<Server*>(context);
    for (int i = 0; i < server.replies; ++i) {
        HANDLE pipe = CreateNamedPipeW(L"\\\\.\\pipe\\FaceKidsAuthPipe", PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT, 1, 4096, 4096, 0, nullptr);
        if (pipe == INVALID_HANDLE_VALUE) return 1;
        SetEvent(server.ready);
        if (!ConnectNamedPipe(pipe, nullptr) && GetLastError() != ERROR_PIPE_CONNECTED) return 2;
        char request[128] = {};
        DWORD count = 0;
        if (!ReadFile(pipe, request, sizeof(request), &count, nullptr)) return 3;
        ++server.requests;
        SetEvent(server.received);
        if (WaitForSingleObject(server.releaseReply, 5000) != WAIT_OBJECT_0) return 4;
        std::string response = i + 1 == server.replies
            ? "{\"status\":\"ALLOW\",\"user\":\"Filhos\",\"child_id\":2,\"child_name\":\"TestChild\","
              "\"protocol_marker\":\"FACEKIDS_IPC_V1\",\"timestamp\":" + std::to_string(time(nullptr)) + "}"
            : "{\"status\":\"DENY_UNKNOWN\"}";
        if (!WriteFile(pipe, response.data(), static_cast<DWORD>(response.size()), &count, nullptr)) return 5;
        FlushFileBuffers(pipe);
        DisconnectNamedPipe(pipe);
        CloseHandle(pipe);
    }
    return 0;
}

static void Require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1); // Also terminates a pending fake server on test failure.
    }
}

static void FinishServer(HANDLE thread, Server& server) {
    Require(WaitForSingleObject(thread, 6000) == WAIT_OBJECT_0, "fake server timeout");
    DWORD exitCode = 1;
    GetExitCodeThread(thread, &exitCode);
    Require(exitCode == 0, "fake server failed");
    CloseHandle(thread);
    CloseHandle(server.ready);
    CloseHandle(server.received);
    CloseHandle(server.releaseReply);
}

static void WaitForWorkerExit() {
    const ULONGLONG deadline = GetTickCount64() + 8500;
    while (InterlockedCompareExchange(&g_cObjects, 0, 0) != 0 && GetTickCount64() < deadline) Sleep(25);
    Require(InterlockedCompareExchange(&g_cObjects, 0, 0) == 0, "credential worker leaked after UnAdvise");
}

int main() {
    {
        Server server;
        HANDLE thread = CreateThread(nullptr, 0, Serve, &server, 0, nullptr);
        Require(thread && WaitForSingleObject(server.ready, 3000) == WAIT_OBJECT_0, "server startup");
        auto* credential = new FaceKidsCredential(nullptr);
        credential->Advise(nullptr);
        bool recognized = false;
        const ULONGLONG deadline = GetTickCount64() + 10000;
        while (GetTickCount64() < deadline) {
            PWSTR status = nullptr;
            credential->GetStringValue(FIELD_STATUS, &status);
            recognized = status && std::wstring(status).find(L"Desbloqueando") != std::wstring::npos;
            CoTaskMemFree(status);
            if (recognized) break;
            Sleep(25);
        }
        Require(recognized && server.requests == 2, "DENY must retry automatically, then accept ALLOW");
        credential->UnAdvise();
        credential->Release();
        WaitForWorkerExit();
        FinishServer(thread, server);
        std::cout << "PASS: recognition retries without clicks; worker exits after UnAdvise\n";
    }
    {
        Server server;
        server.replies = 1;
        ResetEvent(server.releaseReply);
        HANDLE thread = CreateThread(nullptr, 0, Serve, &server, 0, nullptr);
        Require(thread && WaitForSingleObject(server.ready, 3000) == WAIT_OBJECT_0, "server startup");
        auto* credential = new FaceKidsCredential(nullptr);
        credential->Advise(nullptr);
        Require(WaitForSingleObject(server.received, 3000) == WAIT_OBJECT_0, "request not received");
        credential->SetDeselected();
        SetEvent(server.releaseReply); // ALLOW now belongs to the old activation.
        FinishServer(thread, server);
        Sleep(100);
        CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE response;
        CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION serialization = {};
        PWSTR text = nullptr;
        CREDENTIAL_PROVIDER_STATUS_ICON icon;
        credential->GetSerialization(&response, &serialization, &text, &icon);
        Require(response == CPGSR_NO_CREDENTIAL_NOT_FINISHED && serialization.cbSerialization == 0,
                "late ALLOW after deselection must not serialize credentials");
        CoTaskMemFree(text);
        credential->UnAdvise();
        credential->Release();
        WaitForWorkerExit();
        std::cout << "PASS: late authorization discarded after deselection\n";
    }
    {
        Server server;
        server.replies = 1;
        ResetEvent(server.releaseReply);
        HANDLE thread = CreateThread(nullptr, 0, Serve, &server, 0, nullptr);
        Require(thread && WaitForSingleObject(server.ready, 3000) == WAIT_OBJECT_0, "server startup");
        auto* provider = new FaceKidsProvider();
        auto* credential = provider->HostTestCredential();
        credential->Advise(nullptr);
        Require(WaitForSingleObject(server.received, 3000) == WAIT_OBJECT_0, "request not received");
        provider->Release(); // Pending worker must keep the parent alive.
        SetEvent(server.releaseReply);
        FinishServer(thread, server);
        const ULONGLONG deadline = GetTickCount64() + 3000;
        while (InterlockedCompareExchange(&g_cObjects, 0, 0) != 1 && GetTickCount64() < deadline) Sleep(25);
        Require(InterlockedCompareExchange(&g_cObjects, 0, 0) == 1,
                "parent not released after worker completion");
        // Credential can outlive its provider as an independent COM reference.
        // These callbacks must not dereference the now-destroyed parent.
        credential->SetDeselected();
        credential->UnAdvise();
        credential->Release();
        WaitForWorkerExit();
        std::cout << "PASS: credential survives parent release without dangling callbacks\n";
    }
    return 0;
}
