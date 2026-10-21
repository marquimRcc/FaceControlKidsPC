#pragma once
#include "common.h"

struct AuthResult {
    bool success = false;
    std::wstring user;
    std::wstring password;
    std::wstring message;
    std::wstring childName;
    int remainingSeconds = 0;
};

class FaceKidsPipeClient {
public:
    static AuthResult RequestAuthentication() {
        AuthResult result;
        const LPCWSTR pipeName = L"\\\\.\\pipe\\FaceKidsAuthPipe";

        HANDLE hPipe = INVALID_HANDLE_VALUE;
        const DWORD timeoutMs = 4000;
        const DWORD startTime = GetTickCount();

        while (GetTickCount() - startTime < timeoutMs) {
            hPipe = CreateFileW(
                pipeName,
                GENERIC_READ | GENERIC_WRITE,
                0,
                nullptr,
                OPEN_EXISTING,
                0,
                nullptr
            );

            if (hPipe != INVALID_HANDLE_VALUE) {
                break;
            }

            DWORD err = GetLastError();
            if (err == ERROR_PIPE_BUSY) {
                WaitNamedPipeW(pipeName, 500);
            } else {
                Sleep(150);
            }
        }

        if (hPipe == INVALID_HANDLE_VALUE) {
            result.message = L"Servico FaceKids nao esta em execucao.";
            return result;
        }

        const char* request = "AUTH_QUERY\n";
        DWORD bytesWritten = 0;
        WriteFile(hPipe, request, (DWORD)strlen(request), &bytesWritten, nullptr);

        char buffer[2048] = {};
        DWORD bytesRead = 0;
        BOOL readOk = ReadFile(hPipe, buffer, sizeof(buffer) - 1, &bytesRead, nullptr);
        CloseHandle(hPipe);

        if (!readOk || bytesRead == 0) {
            result.message = L"Sem resposta do servico.";
            return result;
        }

        buffer[bytesRead] = '\0';
        std::string resp(buffer);

        if (resp.find("\"ALLOW\"") != std::string::npos) {
            result.success = true;
            result.user = L"Filhos";
            result.password = L"1";

            size_t namePos = resp.find("\"child_name\": \"");
            if (namePos != std::string::npos) {
                namePos += 15;
                size_t endPos = resp.find("\"", namePos);
                if (endPos != std::string::npos) {
                    std::string n = resp.substr(namePos, endPos - namePos);
                    result.childName = std::wstring(n.begin(), n.end());
                }
            }

            result.message = L"Rosto reconhecido! Desbloqueando...";
        } else if (resp.find("DENY_QUOTA") != std::string::npos) {
            result.success = false;
            result.message = L"Tempo diario esgotado para esta crianca.";
        } else if (resp.find("DENY_UNKNOWN") != std::string::npos) {
            result.success = false;
            result.message = L"Rosto nao reconhecido. Aproxime-se e tente novamente.";
        } else if (resp.find("DENY_NO_FACE") != std::string::npos) {
            result.success = false;
            result.message = L"Nenhum rosto visivel para a camera.";
        } else {
            result.success = false;
            result.message = L"Identificando... Olhe para a webcam.";
        }

        return result;
    }
};
