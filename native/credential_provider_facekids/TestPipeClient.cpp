#define WIN32_LEAN_AND_MEAN
#include "FaceKidsPipeClient.h"
#include <iostream>
#include <cassert>

static int RunParsingUnitTests() {
    std::wcout << L"[FaceKids Pipe Unit Tests] Executando testes unitarios do parser...\n";

    // 1. ALLOW valido
    std::string allowJson = "{\"status\": \"ALLOW\", \"user\": \"Filhos\", \"password\": \"1\", \"child_name\": \"Crianca 2\", \"remaining\": 7200}";
    AuthResult r1 = FaceKidsPipeClient::ParseResponse(allowJson);
    if (!r1.success || r1.user != L"Filhos" || r1.password != L"1" || r1.childName != L"Crianca 2") {
        std::wcerr << L"[FALHA] Teste 1 (ALLOW valido) falhou!\n";
        return 1;
    }
    std::wcout << L"  [PASS] 1. ALLOW valido reconhecido corretamente.\n";

    // 2. Fake ALLOW no corpo da mensagem deve ser NEGADO
    std::string fakeAllowJson = "{\"status\": \"DENY_UNKNOWN\", \"data\": {\"message\": \"Cannot ALLOW this user\"}}";
    AuthResult r2 = FaceKidsPipeClient::ParseResponse(fakeAllowJson);
    if (r2.success) {
        std::wcerr << L"[FALHA] Teste 2 (Fake ALLOW) foi aceito incorretamente!\n";
        return 2;
    }
    std::wcout << L"  [PASS] 2. Fake ALLOW na mensagem rejeitado com seguranca.\n";

    // 3. DENY_QUOTA
    std::string quotaJson = "{\"status\": \"DENY_QUOTA\", \"data\": {\"remaining\": 0}}";
    AuthResult r3 = FaceKidsPipeClient::ParseResponse(quotaJson);
    if (r3.success) {
        std::wcerr << L"[FALHA] Teste 3 (DENY_QUOTA) foi aceito!\n";
        return 3;
    }
    std::wcout << L"  [PASS] 3. DENY_QUOTA rejeitado com status correto.\n";

    // 4. DENY_CURFEW
    std::string curfewJson = "{\"status\": \"DENY_CURFEW\", \"data\": {\"message\": \"Horario nao permitido\"}}";
    AuthResult r4 = FaceKidsPipeClient::ParseResponse(curfewJson);
    if (r4.success) {
        std::wcerr << L"[FALHA] Teste 4 (DENY_CURFEW) foi aceito!\n";
        return 4;
    }
    std::wcout << L"  [PASS] 4. DENY_CURFEW rejeitado com status correto.\n";

    // 5. JSON vazio / invalido
    AuthResult r5 = FaceKidsPipeClient::ParseResponse("");
    if (r5.success) {
        std::wcerr << L"[FALHA] Teste 5 (JSON vazio) foi aceito!\n";
        return 5;
    }
    std::wcout << L"  [PASS] 5. JSON vazio tratado com seguranca.\n";

    std::wcout << L"[OK] Todos os testes unitarios de parsing passaram com 100% de sucesso!\n\n";
    return 0;
}

int main(int argc, char* argv[]) {
    int testRc = RunParsingUnitTests();
    if (testRc != 0) {
        return testRc;
    }

    // Se chamado apenas para testes unitarios, encerra aqui
    if (argc > 1 && std::string(argv[1]) == "--unit-only") {
        return 0;
    }

    std::wcout << L"[FaceKids Pipe Test] Solicitando autenticacao via \\\\.\\pipe\\FaceKidsAuthPipe...\n";
    AuthResult res = FaceKidsPipeClient::RequestAuthentication();
    std::wcout << L"[Resultado] Sucesso: " << (res.success ? L"SIM" : L"NAO") << L"\n";
    std::wcout << L"[Mensagem] " << res.message << L"\n";
    if (res.success) {
        std::wcout << L"[Usuario]  " << res.user << L"\n";
        std::wcout << L"[Filho]    " << res.childName << L"\n";
    }
    return 0;
}
