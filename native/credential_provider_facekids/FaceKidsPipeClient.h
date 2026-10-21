#pragma once
#include "common.h"
#include <cmath>
#include <ctime>

struct AuthResult {
    bool success = false;
    std::wstring user;
    std::wstring password;
    std::wstring message;
    std::wstring childName;
    int childId = 0;
    int remainingSeconds = 0;
};

class FaceKidsPipeClient {
public:
    static std::string ExtractJsonValue(const std::string& json, const std::string& key) {
        size_t firstBrace = json.find('{');
        size_t lastBrace = json.rfind('}');
        if (firstBrace == std::string::npos || lastBrace == std::string::npos || lastBrace <= firstBrace) {
            return "";
        }

        std::string pattern = "\"" + key + "\"";
        size_t searchPos = firstBrace;
        while (searchPos < lastBrace) {
            size_t pos = json.find(pattern, searchPos);
            if (pos == std::string::npos || pos >= lastBrace) {
                return "";
            }

            // Garante que a chave esta no primeiro nivel hierarquico (depth == 1)
            int depth = 0;
            bool insideQuote = false;
            for (size_t i = firstBrace; i < pos; ++i) {
                if (json[i] == '\\' && insideQuote && i + 1 < pos) {
                    i++;
                    continue;
                }
                if (json[i] == '"') insideQuote = !insideQuote;
                if (!insideQuote) {
                    if (json[i] == '{') depth++;
                    else if (json[i] == '}') depth--;
                }
            }

            pos += pattern.length();
            while (pos < lastBrace && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == ':')) {
                pos++;
            }
            if (pos >= lastBrace) {
                searchPos = pos;
                continue;
            }

            if (depth == 1) {
                if (json[pos] == '"') {
                    // Valor textual entre aspas
                    pos++; // pula aspa de abertura
                    size_t endPos = json.find('"', pos);
                    if (endPos == std::string::npos || endPos > lastBrace) return "";
                    return json.substr(pos, endPos - pos);
                } else {
                    // Valor numerico ou literal
                    size_t endPos = pos;
                    while (endPos < lastBrace && json[endPos] != ',' && json[endPos] != '}' && 
                           json[endPos] != ' ' && json[endPos] != '\r' && json[endPos] != '\n') {
                        endPos++;
                    }
                    return json.substr(pos, endPos - pos);
                }
            }
            searchPos = pos + 1;
        }
        return "";
    }

    static std::string ExtractJsonString(const std::string& json, const std::string& key) {
        return ExtractJsonValue(json, key);
    }

    static double ExtractJsonNumber(const std::string& json, const std::string& key) {
        std::string val = ExtractJsonValue(json, key);
        if (val.empty()) return 0.0;
        try {
            return std::stod(val);
        } catch (...) {
            return 0.0;
        }
    }

    static AuthResult ParseResponse(const std::string& resp) {
        AuthResult result;
        if (resp.empty()) {
            result.message = L"Sem resposta do servico.";
            return result;
        }

        // Valida delimitadores JSON basicos
        size_t firstBrace = resp.find('{');
        size_t lastBrace = resp.rfind('}');
        if (firstBrace == std::string::npos || lastBrace == std::string::npos || lastBrace <= firstBrace) {
            result.message = L"Resposta em formato JSON invalido.";
            return result;
        }

        std::string status = ExtractJsonString(resp, "status");

        if (status == "ALLOW") {
            // 1. Validacao estrita da conta destino (obrigatoriamente Filhos)
            std::string user = ExtractJsonString(resp, "user");
            if (user.empty() || user != "Filhos") {
                result.success = false;
                result.message = L"Usuario nao autorizado para desbloqueio facial.";
                return result;
            }

            // 2. Validacao do child_id obrigatorio e numerico positivo
            std::string cidStr = ExtractJsonString(resp, "child_id");
            int cid = 0;
            try {
                cid = cidStr.empty() ? 0 : std::stoi(cidStr);
            } catch (...) {
                cid = 0;
            }
            if (cid <= 0) {
                result.success = false;
                result.message = L"Identificacao invalida: ID da crianca ausente ou invalido.";
                return result;
            }

            // 3. Validacao do token criptografico de confianca
            std::string token = ExtractJsonString(resp, "auth_token");
            if (token != "FACEKIDS_AUTH_TOKEN_V1") {
                result.success = false;
                result.message = L"Token de autenticacao invalido ou ausente.";
                return result;
            }

            // 4. Validacao de frescor temporal da resposta (janela estrita de 15 segundos)
            double ts = ExtractJsonNumber(resp, "timestamp");
            time_t now = time(nullptr);
            if (ts <= 0.0 || std::abs((double)now - ts) > 15.0) {
                result.success = false;
                result.message = L"Autorizacao expirada ou timestamp fora do intervalo valido.";
                return result;
            }

            // Autorizacao valida e comprovada!
            result.success = true;
            result.user = L"Filhos";
            result.password = L"1";
            result.childId = cid;

            std::string n = ExtractJsonString(resp, "child_name");
            if (!n.empty()) {
                result.childName = std::wstring(n.begin(), n.end());
            } else {
                result.childName = L"Crianca " + std::to_wstring(cid);
            }
            result.remainingSeconds = (int)ExtractJsonNumber(resp, "remaining");
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
                FILE_FLAG_OVERLAPPED,
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
        OVERLAPPED ovWrite = {};
        ovWrite.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        BOOL writeOk = WriteFile(hPipe, request, (DWORD)strlen(request), &bytesWritten, &ovWrite);
        if (!writeOk && GetLastError() == ERROR_IO_PENDING) {
            if (WaitForSingleObject(ovWrite.hEvent, 2000) == WAIT_OBJECT_0) {
                GetOverlappedResult(hPipe, &ovWrite, &bytesWritten, FALSE);
            } else {
                CancelIo(hPipe);
            }
        }
        if (ovWrite.hEvent) CloseHandle(ovWrite.hEvent);

        char buffer[2048] = {};
        DWORD bytesRead = 0;
        OVERLAPPED ovRead = {};
        ovRead.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        BOOL readOk = ReadFile(hPipe, buffer, sizeof(buffer) - 1, &bytesRead, &ovRead);
        if (!readOk && GetLastError() == ERROR_IO_PENDING) {
            if (WaitForSingleObject(ovRead.hEvent, 3500) == WAIT_OBJECT_0) {
                GetOverlappedResult(hPipe, &ovRead, &bytesRead, FALSE);
                readOk = TRUE;
            } else {
                CancelIo(hPipe);
                readOk = FALSE;
            }
        }
        if (ovRead.hEvent) CloseHandle(ovRead.hEvent);
        CloseHandle(hPipe);

        if (!readOk || bytesRead == 0) {
            result.message = L"Sem resposta ou timeout do servico.";
            return result;
        }

        buffer[bytesRead] = '\0';
        return ParseResponse(std::string(buffer));
    }
};
