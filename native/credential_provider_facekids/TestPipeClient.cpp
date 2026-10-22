#define WIN32_LEAN_AND_MEAN
#include "FaceKidsPipeClient.h"
#include <iostream>
#include <cassert>
#include <ctime>

static int RunParsingUnitTests() {
    std::wcout << L"[FaceKids Pipe Unit Tests] Executando testes unitarios do parser...\n";

    time_t now = time(nullptr);
    std::string nowTs = std::to_string(now);

    // O timeout total precisa acomodar os 4,5 s do reconhecimento + transporte.
    if (FaceKidsPipeClient::kTotalRequestTimeoutMs <= FaceKidsPipeClient::kRecognitionBudgetMs) {
        std::wcerr << L"[FALHA] Timeout total nao acomoda reconhecimento facial.\n";
        return 1;
    }

    // 1. ALLOW valido completo com user, child_id, marcador e timestamp fresco
    std::string allowJson = "{\"status\": \"ALLOW\", \"user\": \"Filhos\", \"password\": \"1\", \"child_id\": 2, \"child_name\": \"Crianca 2\", \"remaining\": 7200, \"protocol_marker\": \"FACEKIDS_IPC_V1\", \"timestamp\": " + nowTs + "}";
    AuthResult r1 = FaceKidsPipeClient::ParseResponse(allowJson);
    if (!r1.success || r1.user != L"Filhos" || r1.password != L"1" || r1.childId != 2 || r1.childName != L"Crianca 2") {
        std::wcerr << L"[FALHA] Teste 1 (ALLOW valido) falhou! Msg: " << r1.message << L"\n";
        return 1;
    }
    std::wcout << L"  [PASS] 1. ALLOW valido reconhecido corretamente.\n";

    // 2. Rejeicao de ALLOW sem o campo "user"
    std::string noUserJson = "{\"status\": \"ALLOW\", \"child_id\": 2, \"protocol_marker\": \"FACEKIDS_IPC_V1\", \"timestamp\": " + nowTs + "}";
    AuthResult r2 = FaceKidsPipeClient::ParseResponse(noUserJson);
    if (r2.success) {
        std::wcerr << L"[FALHA] Teste 2 (ALLOW sem user) foi aceito incorretamente!\n";
        return 2;
    }
    std::wcout << L"  [PASS] 2. ALLOW sem campo 'user' rejeitado com seguranca.\n";

    // 3. Rejeicao de ALLOW sem child_id
    std::string noCidJson = "{\"status\": \"ALLOW\", \"user\": \"Filhos\", \"protocol_marker\": \"FACEKIDS_IPC_V1\", \"timestamp\": " + nowTs + "}";
    AuthResult r3 = FaceKidsPipeClient::ParseResponse(noCidJson);
    if (r3.success) {
        std::wcerr << L"[FALHA] Teste 3 (ALLOW sem child_id) foi aceito incorretamente!\n";
        return 3;
    }
    std::wcout << L"  [PASS] 3. ALLOW sem 'child_id' valido rejeitado com seguranca.\n";

    // 4. Rejeicao de ALLOW com marcador de protocolo ausente ou invalido
    std::string badMarkerJson = "{\"status\": \"ALLOW\", \"user\": \"Filhos\", \"child_id\": 2, \"protocol_marker\": \"INVALID_PROTOCOL\", \"timestamp\": " + nowTs + "}";
    AuthResult r4 = FaceKidsPipeClient::ParseResponse(badMarkerJson);
    if (r4.success) {
        std::wcerr << L"[FALHA] Teste 4 (ALLOW com protocolo invalido) foi aceito!\n";
        return 4;
    }
    std::wcout << L"  [PASS] 4. Marcador de protocolo invalido rejeitado.\n";

    // 5. Rejeicao de timestamp expirado (60 segundos atras)
    std::string expiredTs = std::to_string(now - 60);
    std::string staleJson = "{\"status\": \"ALLOW\", \"user\": \"Filhos\", \"child_id\": 2, \"protocol_marker\": \"FACEKIDS_IPC_V1\", \"timestamp\": " + expiredTs + "}";
    AuthResult r5 = FaceKidsPipeClient::ParseResponse(staleJson);
    if (r5.success) {
        std::wcerr << L"[FALHA] Teste 5 (Timestamp expirado) foi aceito!\n";
        return 5;
    }
    std::wcout << L"  [PASS] 5. Timestamp expirado rejeitado com seguranca.\n";

    // 6. Fake ALLOW no corpo da mensagem deve ser NEGADO
    std::string fakeAllowJson = "{\"status\": \"DENY_UNKNOWN\", \"data\": {\"message\": \"Cannot ALLOW this user\"}}";
    AuthResult r6 = FaceKidsPipeClient::ParseResponse(fakeAllowJson);
    if (r6.success) {
        std::wcerr << L"[FALHA] Teste 6 (Fake ALLOW) foi aceito incorretamente!\n";
        return 6;
    }
    std::wcout << L"  [PASS] 6. Fake ALLOW na mensagem rejeitado com seguranca.\n";

    // 7. DENY_QUOTA
    std::string quotaJson = "{\"status\": \"DENY_QUOTA\", \"data\": {\"remaining\": 0}}";
    AuthResult r7 = FaceKidsPipeClient::ParseResponse(quotaJson);
    if (r7.success) {
        std::wcerr << L"[FALHA] Teste 7 (DENY_QUOTA) foi aceito como sucesso!\n";
        return 7;
    }
    std::wcout << L"  [PASS] 7. DENY_QUOTA rejeitado com status correto.\n";

    // 8. DENY_CURFEW
    std::string curfewJson = "{\"status\": \"DENY_CURFEW\", \"data\": {\"message\": \"Horario nao permitido\"}}";
    AuthResult r8 = FaceKidsPipeClient::ParseResponse(curfewJson);
    if (r8.success) {
        std::wcerr << L"[FALHA] Teste 8 (DENY_CURFEW) foi aceito como sucesso!\n";
        return 8;
    }
    std::wcout << L"  [PASS] 8. DENY_CURFEW rejeitado com status correto.\n";

    // 9. JSON vazio / invalido
    AuthResult r9 = FaceKidsPipeClient::ParseResponse("");
    if (r9.success) {
        std::wcerr << L"[FALHA] Teste 9 (JSON vazio) foi aceito!\n";
        return 9;
    }
    std::wcout << L"  [PASS] 9. JSON vazio tratado com seguranca.\n";

    // 10. JSON sem delimitadores validos
    AuthResult r10 = FaceKidsPipeClient::ParseResponse("status: ALLOW, user: Filhos");
    if (r10.success) {
        std::wcerr << L"[FALHA] Teste 10 (JSON sem delimitadores) foi aceito!\n";
        return 10;
    }
    std::wcout << L"  [PASS] 10. JSON sem delimitadores rejeitado com seguranca.\n";

    // 11. Rejeicao de usuario que nao seja Filhos (ex: Administrator)
    std::string adminJson = "{\"status\": \"ALLOW\", \"user\": \"Administrator\", \"child_id\": 2, \"protocol_marker\": \"FACEKIDS_IPC_V1\", \"timestamp\": " + nowTs + "}";
    AuthResult r11 = FaceKidsPipeClient::ParseResponse(adminJson);
    if (r11.success) {
        std::wcerr << L"[FALHA] Teste 11 (ALLOW para Administrator) foi aceito incorretamente!\n";
        return 11;
    }
    std::wcout << L"  [PASS] 11. Rejeicao de conta que nao seja 'Filhos' aprovada.\n";

    // 12. Fake status ALLOW em objeto aninhado data
    std::string nestedFakeJson = "{\"data\": {\"status\": \"ALLOW\"}, \"status\": \"DENY_UNKNOWN\"}";
    AuthResult r12 = FaceKidsPipeClient::ParseResponse(nestedFakeJson);
    if (r12.success) {
        std::wcerr << L"[FALHA] Teste 12 (Status aninhado) foi aceito incorretamente como ALLOW!\n";
        return 12;
    }
    std::wcout << L"  [PASS] 12. Status aninhado em data rejeitado com sucesso.\n";

    std::wcout << L"[OK] Todos os 12 testes unitarios de parsing passaram com 100% de sucesso!\n\n";
    return 0;
}

int main(int argc, char* argv[]) {
    int testRc = RunParsingUnitTests();
    if (testRc != 0) {
        return testRc;
    }

    if (argc > 1 && std::string(argv[1]) == "--unit-only") {
        return 0;
    }

    std::wcout << L"[FaceKids Pipe Test] Solicitando autenticacao via \\\\.\\pipe\\FaceKidsAuthPipe...\n";
    ULONGLONG started = GetTickCount64();
    AuthResult res = FaceKidsPipeClient::RequestAuthentication();
    ULONGLONG elapsed = GetTickCount64() - started;
    if (elapsed > FaceKidsPipeClient::kTotalRequestTimeoutMs + 1500) {
        std::wcerr << L"[FALHA] Cliente excedeu o prazo global: " << elapsed << L" ms.\n";
        return 13;
    }
    std::wcout << L"[Tempo] " << elapsed << L" ms (limite global controlado)\n";
    std::wcout << L"[Resultado] Sucesso: " << (res.success ? L"SIM" : L"NAO") << L"\n";
    std::wcout << L"[Mensagem] " << res.message << L"\n";
    if (res.success) {
        std::wcout << L"[Usuario]  " << res.user << L"\n";
        std::wcout << L"[Filho]    " << res.childName << L" (ID: " << res.childId << L")\n";
    }
    return 0;
}
