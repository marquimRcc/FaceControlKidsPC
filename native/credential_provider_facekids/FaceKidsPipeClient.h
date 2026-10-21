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
    static std::string ExtractJsonString(const std::string& json, const std::string& key) {
        std::string pattern = "\"" + key + "\"";
        size_t pos = json.find(pattern);
        if (pos == std::string::npos) return "";
        pos += pattern.length();
        while (pos < json.length() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == ':')) {
            pos++;
        }
        if (pos >= json.length() || json[pos] != '"') return "";
        pos++; // Skip opening quote
        size_t endPos = json.find('"', pos);
        if (endPos == std::string::npos) return "";
        return json.substr(pos, endPos - pos);
    }

    static AuthResult ParseResponse(const std::string& resp) {
        AuthResult result;
        if (resp.empty()) {
            result.message = L"Sem resposta do servico.";
            return result;
        }

        std::string status = ExtractJsonString(resp, "status");

        if (status == "ALLOW") {
            result.success = true;
            result.user = L"Filhos";
            result.password = L"1";

            std::string n = ExtractJsonString(resp, "child_name");
            if (!n.empty()) {
                result.childName = std::wstring(n.begin(), n.end());
            }
            result.message = L"Rosto reconhecido! Desbloqueando...";
        } else if (status == "DENY_QUOTA") {
            result.success = false;
            result.message = L"Tempo diario esgotado para esta crianca.";
        } else if (status == "DENY_CURFEW") {
            result.success = false;
            result.message = L"Horario de uso nao permitido para esta crianca.";
        } else if (status == "DENY_UNKNOWN") {
            result.success = false;
            result.message = L"Rosto nao reconhecido. Aproxime-se e tente novamente.";
        } else if (status == "DENY_NO_ENROLLMENT") {
            result.success = false;
            result.message = L"Nenhum rosto cadastrado no sistema.";
        } else if (status == "DENY_NO_FACE") {
            result.success = false;
            result.message = L"Nenhum rosto visivel para a camera.";
        } else if (status == "ERROR_CAMERA") {
            result.success = false;
            result.message = L"Camera indisponivel no momento.";
        } else {
            result.success = false;
            result.message = L"Identificando... Olhe para a webcam.";
        }

        return result;
    }

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
        return ParseResponse(std::string(buffer));
    }
};
